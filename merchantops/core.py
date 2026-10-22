"""Version 3 source contract. Immutable events; integer INR paise."""

from datetime import date, timedelta
from random import Random
from pathlib import Path
import csv, tempfile, json, hashlib
import duckdb

COLUMNS = {
    "orders": [
        "order_id",
        "customer_id",
        "ordered_at",
        "channel",
        "shipping",
        "currency",
    ],
    "line_items": [
        "line_id",
        "order_id",
        "product",
        "quantity",
        "unit_price",
        "discount",
        "unit_cost",
    ],
    "refunds": ["refund_id", "line_id", "refunded_at", "amount"],
    "payments": [
        "payment_id",
        "order_id",
        "occurred_at",
        "kind",
        "status",
        "amount",
        "fee",
    ],
    "spend": ["spend_id", "spent_at", "channel", "amount"],
}
TYPES = {
    "orders": ["varchar", "varchar", "date", "varchar", "bigint", "varchar"],
    "line_items": [
        "varchar",
        "varchar",
        "varchar",
        "bigint",
        "bigint",
        "bigint",
        "bigint",
    ],
    "refunds": ["varchar", "varchar", "date", "bigint"],
    "payments": [
        "varchar",
        "varchar",
        "date",
        "varchar",
        "varchar",
        "bigint",
        "bigint",
    ],
    "spend": ["varchar", "date", "varchar", "bigint"],
}
FIELDS = {k: len(v) for k, v in COLUMNS.items()}


def connect(path=":memory:"):
    c = duckdb.connect(str(path))
    if c.execute(
        "select count(*) from information_schema.tables where table_name='orders'"
    ).fetchone()[0]:
        fields = [r[0] for r in c.execute("describe orders").fetchall()]
        if fields != COLUMNS["orders"] + ["_batch_id"]:
            c.close()
            raise ValueError(
                "Legacy schema: use a new v3 database; no automatic migration"
            )
    for table, columns in COLUMNS.items():
        fields = ",".join(
            f"{name} {kind} not null" + (" primary key" if i == 0 else "")
            for i, (name, kind) in enumerate(zip(columns, TYPES[table]))
        )
        c.execute(
            f"create table if not exists {table} ({fields}, _batch_id bigint not null)"
        )
    c.execute(
        """create table if not exists quarantine(batch_hash varchar primary key,
 rejected_at timestamp default current_timestamp,reason varchar,payload varchar);
 create table if not exists ingestion_batches(batch_id bigint primary key,batch_hash varchar,inserted_rows bigint);
 create table if not exists pipeline_state(id integer primary key,processed_batch bigint,as_of date);
 insert into pipeline_state(id,processed_batch,as_of) values(1,0,date '2026-06-30') on conflict do nothing;"""
    )
    c.execute(
        "alter table pipeline_state add column if not exists ready boolean default false"
    )
    return c


def ingest(c, batch):
    payload = json.dumps(batch, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    c.execute("begin")
    try:
        if not isinstance(batch, dict) or set(batch) - set(COLUMNS):
            raise ValueError("Unknown source table: schema drift")
        batch_id = c.execute(
            "select coalesce(max(batch_id),0)+1 from ingestion_batches"
        ).fetchone()[0]
        inserted = 0
        for table, columns in COLUMNS.items():
            rows = batch.get(table, [])
            if not isinstance(rows, list):
                raise ValueError("Rows must be a list")
            unique = {}
            for raw in rows:
                if not isinstance(raw, (list, tuple)) or len(raw) != len(columns):
                    raise ValueError(f"{table}: invalid row shape")
                row = list(raw)
                for i, (name, kind) in enumerate(zip(columns, TYPES[table])):
                    if kind == "bigint" and (
                        type(row[i]) is not int or row[i] < 0 or row[i] > 10**12
                    ):
                        raise ValueError(
                            f"{table}.{name}: expected nonnegative integer ≤ 10^12"
                        )
                    if kind == "varchar" and (
                        not isinstance(row[i], str) or not row[i].strip()
                    ):
                        raise ValueError(f"{table}.{name}: empty string")
                    if kind == "date":
                        row[i] = date.fromisoformat(str(row[i]))
                if table == "orders" and row[5] != "INR":
                    raise ValueError(
                        "Only INR supported; currency conversion is not implicit"
                    )
                if table == "line_items" and (
                    row[3] < 1 or row[3] > 10000 or row[5] > row[3] * row[4]
                ):
                    raise ValueError("Invalid quantity or line discount")
                if table == "payments" and (
                    row[3] not in ("capture", "refund")
                    or row[4] not in ("succeeded", "failed")
                    or (row[4] == "failed" and row[6] != 0)
                ):
                    raise ValueError(
                        "Invalid payment kind, status or failed-payment fee"
                    )
                if row[0] in unique and unique[row[0]] != row:
                    raise ValueError("Conflicting event ID within batch")
                unique[row[0]] = row
            if not unique:
                continue
            c.execute(
                f'create or replace temp table stage as select {",".join(columns)} from {table} limit 0'
            )
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "batch.csv"
                with path.open("w", newline="") as stream:
                    csv.writer(stream, lineterminator="\n").writerows(unique.values())
                safe = str(path).replace("'", "''")
                c.execute(
                    f"copy stage from '{safe}' (format csv,header false,auto_detect false,delim ',',quote '\"',escape '\"')"
                )
            key = columns[0]
            changed = " or ".join(
                f"s.{col} is distinct from t.{col}" for col in columns
            )
            if c.execute(
                f"select 1 from stage s join {table} t using({key}) where {changed} limit 1"
            ).fetchone():
                raise ValueError("Conflicting event ID")
            count = c.execute(
                f"select count(*) from stage s anti join {table} t using({key})"
            ).fetchone()[0]
            c.execute(
                f"insert into {table} select s.*,? from stage s anti join {table} t using({key})",
                [batch_id],
            )
            inserted += count
        checks = [
            (
                "Orphan line item",
                "select 1 from line_items l anti join orders o using(order_id)",
            ),
            (
                "Order requires complete line-item bundle",
                "select 1 from orders o anti join line_items l using(order_id)",
            ),
            (
                "Orphan refund",
                "select 1 from refunds r anti join line_items l using(line_id)",
            ),
            (
                "Refund predates order",
                "select 1 from refunds r join line_items l using(line_id) join orders o using(order_id) where refunded_at<ordered_at",
            ),
            (
                "Cumulative line over-refund",
                "select 1 from refunds r join line_items l using(line_id) group by r.line_id having sum(amount)>max(quantity*unit_price-discount)",
            ),
            (
                "Orphan payment",
                "select 1 from payments p anti join orders o using(order_id)",
            ),
            (
                "Payment predates order",
                "select 1 from payments p join orders o using(order_id) where occurred_at<ordered_at",
            ),
            (
                "Cash refund predates captured funds or granted refund",
                """with events as (
    select order_id,occurred_at as day,case when kind='capture' then amount else -amount end as cash,
    case when kind='refund' then -amount else 0 end as liability from payments where status='succeeded'
    union all select l.order_id,r.refunded_at,0,r.amount from refunds r join line_items l using(line_id)
    ), daily as(select order_id,day,sum(cash) as cash,sum(liability) as liability from events group by all),
    balances as(select sum(cash) over(partition by order_id order by day) as cash_balance,
    sum(liability) over(partition by order_id order by day) as refund_balance from daily)
    select 1 from balances where cash_balance<0 or refund_balance<0""",
            ),
            (
                "Cash exceeds supported order/refund amounts",
                """with charged as(select order_id,sum(quantity*unit_price-discount) as charge from line_items group by order_id),
     credited as(select l.order_id,sum(r.amount) as refunded from refunds r join line_items l using(line_id) group by l.order_id),
     cash as(select order_id,sum(case when kind='capture' and status='succeeded' then amount else 0 end) as captured,
     sum(case when kind='refund' and status='succeeded' then amount else 0 end) as returned from payments group by order_id)
     select 1 from cash join charged using(order_id) left join credited using(order_id)
     where captured>charge or returned>captured or returned>coalesce(refunded,0)""",
            ),
        ]
        for reason, sql in checks:
            if c.execute(sql + " limit 1").fetchone():
                raise ValueError(reason)
        if inserted:
            c.execute(
                "insert into ingestion_batches values(?,?,?)",
                [batch_id, digest, inserted],
            )
        if inserted:
            c.execute("update pipeline_state set ready=false where id=1")
        c.execute("commit")
        return {
            "batch_id": batch_id if inserted else batch_id - 1,
            "inserted_rows": inserted,
        }
    except Exception as error:
        c.execute("rollback")
        c.execute(
            "insert into quarantine(batch_hash,reason,payload) values(?,?,?) on conflict do nothing",
            [digest, str(error), payload],
        )
        raise


def synthetic():
    rng = Random(42)
    b = {k: [] for k in COLUMNS}
    start = date(2026, 1, 1)
    products = [("Everyday tee", 129900), ("Denim", 279900), ("Overshirt", 229900)]
    for day in range(181):
        d = start + timedelta(days=day)
        for channel in ("Organic", "Paid social", "Marketplace"):
            b["spend"].append(
                [
                    f"S{day}-{channel}",
                    str(d),
                    channel,
                    0 if channel == "Organic" else (170000 if d.month < 4 else 390000),
                ]
            )
        for _ in range(8 + d.month * 2):
            i = len(b["orders"])
            oid = f"O{i:05}"
            channel = rng.choice(["Organic", "Paid social", "Marketplace"])
            b["orders"].append(
                [oid, f"C{rng.randrange(850):04}", str(d), channel, 9500, "INR"]
            )
            charge = 0
            for j in range(2 if i % 3 == 0 else 1):
                product, price = rng.choice(products)
                qty = 2 if i % 11 == 0 else 1
                discount = qty * price * (10 if d.month < 4 else 25) // 100
                lid = f"{oid}-L{j}"
                b["line_items"].append(
                    [lid, oid, product, qty, price, discount, price * 42 // 100]
                )
                charge += qty * price - discount
                if rng.random() < (0.06 if d.month < 4 else 0.14):
                    rd = d + timedelta(days=rng.randint(2, 28))
                    amount = (qty * price - discount) // 2
                    if rd <= date(2026, 6, 30):
                        b["refunds"].append([f"R{lid}", lid, str(rd), amount])
            if i % 17 == 0:
                b["payments"].append(
                    [f"{oid}-failed", oid, str(d), "capture", "failed", charge, 0]
                )
            chunks = [charge // 2, charge - charge // 2] if i % 7 == 0 else [charge]
            for j, amount in enumerate(chunks):
                b["payments"].append(
                    [
                        f"{oid}-P{j}",
                        oid,
                        str(d),
                        "capture",
                        "succeeded",
                        amount,
                        amount * 3 // 100,
                    ]
                )
    for i, r in enumerate(b["refunds"]):
        oid = r[1].split("-L")[0]
        if i % 13 != 0:
            b["payments"].append(
                [f"cash-{r[0]}", oid, r[2], "refund", "succeeded", r[3], 0]
            )
    return b


def records(c, sql, params=None):
    cur = c.execute(sql, params or [])
    return [dict(zip([x[0] for x in cur.description], r)) for r in cur.fetchall()]
