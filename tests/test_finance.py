from pathlib import Path
import json
import pytest
from jinja2 import Environment
from merchantops.core import connect, ingest, synthetic
from merchantops.evidence import fixture
from merchantops.pipeline import MODELS


@pytest.fixture
def db():
    c = connect()
    yield c
    c.close()


def model(c, name):
    env = Environment()
    sql = env.from_string(Path(f"models/{name}.sql").read_text()).render(
        config=lambda **kwargs: "",
        ref=lambda n: n,
        source=lambda s, n: n,
        is_incremental=lambda: False,
        var=lambda n, d=None: d,
        changed_orders=lambda: "select order_id from orders",
    )
    c.execute(f"create or replace table {name} as " + sql)


def models(c):
    for name in MODELS:
        model(c, name)


def test_multiline_split_payment_no_fanout(db):
    ingest(db, fixture())
    models(db)
    assert db.execute(
        "select gross,discount,cogs,shipping,fees,net_revenue,contribution_before_ads from order_economics"
    ).fetchone() == (13000, 1000, 4000, 500, 240, 12000, 7260)
    assert db.execute(
        "select captured,cash_net,collection_gap from payment_reconciliation"
    ).fetchone() == (12000, 12000, 0)
    assert db.execute("select sum(contribution) from monthly").fetchone()[0] == 7260


def test_partial_line_refund_and_cash_are_separate(db):
    ingest(db, fixture())
    ingest(db, {"refunds": [["r", "l1", "2026-02-04", 2000]]})
    models(db)
    assert db.execute(
        "select net_revenue from line_economics order by line_id"
    ).fetchall() == [(7000,), (3000,)]
    assert db.execute("select contribution from monthly order by month").fetchall() == [
        (7260,),
        (-2000,),
    ]
    assert db.execute(
        "select refund_payable,cash_net from payment_reconciliation"
    ).fetchone() == (2000, 12000)
    ingest(
        db, {"payments": [["p3", "demo", "2026-02-05", "refund", "succeeded", 2000, 0]]}
    )
    models(db)
    assert db.execute(
        "select refund_payable,cash_net from payment_reconciliation"
    ).fetchone() == (0, 10000)
    assert db.execute("select sum(net_revenue) from monthly").fetchone()[0] == 10000


def test_failed_and_partial_payments_do_not_inflate_revenue(db):
    b = fixture()
    b["payments"] = [
        ["fail", "demo", "2026-01-01", "capture", "failed", 12000, 0],
        ["part", "demo", "2026-01-02", "capture", "succeeded", 5000, 100],
    ]
    ingest(db, b)
    models(db)
    assert db.execute("select net_revenue from order_economics").fetchone()[0] == 12000
    assert db.execute(
        "select captured,collection_gap,failed_attempts from payment_reconciliation"
    ).fetchone() == (5000, 7000, 1)


@pytest.mark.parametrize(
    "table,row,reason",
    [
        ("line_items", ["orphan", "missing", "Tee", 1, 1000, 0, 500], "Orphan line"),
        ("refunds", ["r", "missing", "2026-01-02", 100], "Orphan refund"),
        ("refunds", ["r", "l1", "2025-12-31", 100], "predates"),
        ("refunds", ["r", "l1", "2026-01-02", 9001], "over-refund"),
        (
            "payments",
            ["p3", "demo", "2026-01-02", "capture", "succeeded", 1, 0],
            "Cash exceeds",
        ),
        (
            "payments",
            ["p3", "demo", "2026-01-02", "refund", "succeeded", 1, 0],
            "Cash refund",
        ),
        (
            "payments",
            ["p3", "missing", "2026-01-02", "capture", "succeeded", 1, 0],
            "Orphan payment",
        ),
        (
            "payments",
            ["p3", "demo", "2025-12-31", "capture", "failed", 1, 0],
            "predates",
        ),
        (
            "payments",
            ["p3", "demo", "2026-01-02", "capture", "failed", 1, 1],
            "Invalid payment",
        ),
        ("line_items", ["l3", "demo", "Tee", 0, 1000, 0, 500], "quantity"),
        ("line_items", ["l3", "demo", "Tee", 1, 1000, 1001, 500], "discount"),
        ("spend", ["s", "2026-01-01", "Organic", 1.5], "integer"),
        ("spend", ["s", "2026-01-01", "Organic", -1], "integer"),
    ],
)
def test_invalid_batch_rolls_back_and_quarantines(db, table, row, reason):
    ingest(db, fixture())
    with pytest.raises(ValueError, match=reason):
        ingest(
            db,
            (
                {table: [row], "spend": [["new", "2026-01-01", "Paid social", 10]]}
                if table != "spend"
                else {table: [row]}
            ),
        )
    assert db.execute("select count(*) from quarantine").fetchone()[0] == 1
    assert db.execute("select count(*) from spend").fetchone()[0] == 0
    assert db.execute("select count(*) from ingestion_batches").fetchone()[0] == 1


def test_replay_same_batch_and_cross_batch(db):
    b = fixture()
    b["payments"] += b["payments"][:1]
    first = ingest(db, b)
    replay = ingest(db, b)
    assert first["inserted_rows"] == 5 and replay["inserted_rows"] == 0
    assert replay["batch_id"] == first["batch_id"] == 1
    assert db.execute("select count(*) from payments").fetchone()[0] == 2


def test_conflicting_id_quarantine_deduplicates(db):
    ingest(db, fixture())
    b = fixture()
    b["orders"][0][4] = 600
    for _ in range(2):
        with pytest.raises(ValueError, match="Conflicting"):
            ingest(db, b)
    assert db.execute("select count(*) from quarantine").fetchone()[0] == 1
    assert db.execute("select shipping from orders").fetchone()[0] == 500


def test_cumulative_partial_refunds(db):
    ingest(db, fixture())
    ingest(db, {"refunds": [["r1", "l1", "2026-01-02", 5000]]})
    with pytest.raises(ValueError, match="over-refund"):
        ingest(db, {"refunds": [["r2", "l1", "2026-01-03", 4001]]})
    assert db.execute("select sum(amount) from refunds").fetchone()[0] == 5000


def test_quotes_newlines_and_schema_contract(db):
    b = fixture()
    b["line_items"][0][2] = 'Tee, "blue"\nlarge'
    ingest(db, b)
    ingest(db, b)
    assert (
        db.execute("select product from line_items where line_id='l1'").fetchone()[0]
        == b["line_items"][0][2]
    )
    with pytest.raises(ValueError, match="schema drift"):
        ingest(db, {"orderz": []})
    with pytest.raises(ValueError, match="INR"):
        b = fixture()
        b["orders"][0][0] = "new"
        b["orders"][0][5] = "USD"
        ingest(db, b)


def test_complete_order_bundle_required(db):
    with pytest.raises(ValueError, match="complete line-item"):
        ingest(db, {"orders": fixture()["orders"]})
    assert db.execute("select count(*) from orders").fetchone()[0] == 0


def test_sku_distinct_orders_and_denominators(db):
    b = fixture()
    b["line_items"][1][2] = "Tee"
    ingest(db, b)
    ingest(
        db,
        {
            "refunds": [
                ["r1", "l1", "2026-01-02", 1000],
                ["r2", "l1", "2026-01-03", 500],
            ]
        },
    )
    models(db)
    assert db.execute(
        "select orders,units,refunded_orders,refund_amount,charged_revenue from sku_returns"
    ).fetchone() == (1, 3, 1, 1500, 12000)


def test_retention_and_acquisition_boundary(db):
    b = {"orders": [], "line_items": []}
    for oid, cid, day, channel in [
        ("a", "c", "2026-05-01", "Organic"),
        ("b", "c", "2026-05-31", "Paid social"),
        ("c", "d", "2026-05-01", "Organic"),
        ("d", "d", "2026-06-01", "Organic"),
        ("e", "new", "2026-06-02", "Organic"),
    ]:
        b["orders"].append([oid, cid, day, channel, 0, "INR"])
        b["line_items"].append([oid, oid, "Tee", 1, 100, 0, 40])
    b["spend"] = [["s", "2026-05-01", "Paid social", 50]]
    ingest(db, b)
    models(db)
    assert db.execute(
        "select eligible_customers,repeat_customers,retention_30d from retention"
    ).fetchone() == (2, 1, 0.5)
    assert db.execute(
        "select first_customers,first_order_cac_paise from channel_acquisition where channel='Paid social'"
    ).fetchone() == (0, None)


def test_generator_independent_reconciliation(db):
    b = synthetic()
    assert b == synthetic()
    ingest(db, b)
    ingest(db, b)
    models(db)
    expected = (
        sum(l[3] * (l[4] - l[6]) - l[5] for l in b["line_items"])
        - sum(o[4] for o in b["orders"])
        - sum(r[3] for r in b["refunds"])
        - sum(p[6] for p in b["payments"] if p[4] == "succeeded")
        - sum(s[3] for s in b["spend"])
    )
    assert db.execute("select sum(contribution) from monthly").fetchone()[0] == expected
    assert (
        db.execute("select sum(net_revenue) from sku_returns").fetchone()
        == db.execute("select sum(net_revenue) from order_economics").fetchone()
    )


def test_cash_refund_cannot_precede_grant(db):
    ingest(db, fixture())
    ingest(db, {"refunds": [["r", "l1", "2026-02-04", 1000]]})
    with pytest.raises(ValueError, match="predates"):
        ingest(
            db,
            {
                "payments": [
                    ["early", "demo", "2026-02-03", "refund", "succeeded", 1000, 0]
                ]
            },
        )


def test_fully_discounted_order_and_spend_only_month(db):
    b = {
        "orders": [["free", "c", "2026-01-01", "Organic", 500, "INR"]],
        "line_items": [["l", "free", "Tee", 1, 1000, 1000, 400]],
        "spend": [["s", "2026-02-01", "Paid social", 800]],
    }
    ingest(db, b)
    models(db)
    assert db.execute(
        "select net_revenue,contribution from monthly order by month"
    ).fetchall() == [(0, -900), (0, -800)]
