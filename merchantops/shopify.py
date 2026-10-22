"""Strict Shopify Orders + transaction-history CSV adapter, profile 1.

Offline only. Supplemented costs and provider IDs are required, never inferred.
"""

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import connect, ingest
from .pipeline import database_lock, transform
from .reporting import export_report

ORDER_HEADERS = {
    "Name",
    "Id",
    "Financial Status",
    "Currency",
    "Subtotal",
    "Shipping",
    "Taxes",
    "Total",
    "Discount Amount",
    "Refunded Amount",
    "Created at",
    "Lineitem quantity",
    "Lineitem name",
    "Lineitem price",
    "Lineitem sku",
    "Lineitem discount",
    "Cancelled at",
}
TRANSACTION_HEADERS = {
    "Order",
    "Name",
    "Kind",
    "Gateway",
    "Created At",
    "Status",
    "Amount",
    "Currency",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def money(value):
    require(
        isinstance(value, str)
        and re.fullmatch(r"\d+(?:\.\d{1,2})?", value) is not None,
        "Money must be a nonnegative decimal string with at most two decimals",
    )
    amount = int(Decimal(value) * 100)
    require(amount <= 10**12, "Monetary input exceeds supported range")
    return amount


def text(value):
    require(isinstance(value, str) and bool(value.strip()), "Required text is missing")
    return value.strip()


def stamp(value, timezone):
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise ValueError("Expected timestamp with UTC offset") from None
    require(dt.tzinfo is not None, "Timestamp needs a UTC offset")
    return dt.astimezone(ZoneInfo(timezone)).date().isoformat()


def read_csv(path, required, orders=False):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        raw = reader.fieldnames or []
        # Shopify documentation and exports use both SKU/sku and Canceled/Cancelled.
        aliases = (
            {"Lineitem SKU": "Lineitem sku", "Canceled at": "Cancelled at"}
            if orders
            else {}
        )
        headers = [aliases.get(h, h) for h in raw]
        require(len(headers) == len(set(headers)), "Duplicate CSV headers")
        require(
            required <= set(headers),
            "Missing required CSV headers: "
            + ", ".join(sorted(required - set(headers))),
        )
        reader.fieldnames = headers
        rows = []
        for row in reader:
            require(
                None not in row and None not in row.values(), "Malformed CSV row width"
            )
            rows.append({k: v.strip() for k, v in row.items()})
    require(bool(rows), "Empty CSV export")
    return rows


def transaction_key(row):
    # This identifies a supplemental mapping entry, NOT a guaranteed provider event ID.
    values = {k: row[k] for k in sorted(TRANSACTION_HEADERS)}
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_exports(orders_path, transactions_path):
    rows = read_csv(orders_path, ORDER_HEADERS, orders=True)
    groups = {}
    names = {}
    current = None
    for row in rows:
        if row["Id"]:
            oid = text(row["Id"])
            require(
                oid not in groups,
                "Repeated order header: export orders once with contiguous continuation rows",
            )
            require(
                row["Name"] and row["Name"] not in names,
                "Missing or duplicate order Name",
            )
            groups[oid] = [row]
            names[row["Name"]] = oid
            current = oid
        else:
            require(current is not None, "Orphan continuation row")
            require(
                row["Name"] in ("", groups[current][0]["Name"]),
                "Continuation belongs to a different order",
            )
            # Only line-specific columns and descriptive non-financial fields may differ.
            for field in ORDER_HEADERS - {"Name", "Id"}:
                if not field.startswith("Lineitem") and row[field]:
                    require(
                        row[field] == groups[current][0][field],
                        "Conflicting continuation order field: " + field,
                    )
            groups[current].append(row)
    transactions = read_csv(transactions_path, TRANSACTION_HEADERS)
    keys = [transaction_key(r) for r in transactions]
    require(
        len(keys) == len(set(keys)),
        "Indistinguishable transaction rows: obtain event-level data with IDs",
    )
    return groups, dict(zip(keys, transactions))


def template(orders_path, transactions_path):
    groups, transactions = load_exports(orders_path, transactions_path)
    return {
        "profile": 1,
        "store": None,
        "timezone": None,
        "orders": {
            oid: {
                "customer_id": None,
                "channel": None,
                "shipping_cost": None,
                "unit_costs": {r["Lineitem sku"]: None for r in rows},
            }
            for oid, rows in groups.items()
        },
        "transactions": {
            key: {"transaction_id": None, "fee": None, "reference": row}
            for key, row in transactions.items()
        },
    }


def exact(obj, keys, label):
    require(
        isinstance(obj, dict) and set(obj) == set(keys),
        label + ": unexpected or missing fields",
    )


def convert(orders_path, transactions_path, context, as_of):
    """Return a complete canonical batch + non-PII reconciliation receipt. No writes."""
    exact(
        context, ["profile", "store", "timezone", "orders", "transactions"], "Context"
    )
    require(
        type(context["profile"]) is int and context["profile"] == 1,
        "Unsupported Shopify profile",
    )
    store = text(context["store"])
    require(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", store) is not None,
        "Use a stable lowercase store slug",
    )
    timezone = text(context["timezone"])
    ZoneInfo(timezone)
    cutoff = date.fromisoformat(as_of).isoformat()
    groups, transactions = load_exports(orders_path, transactions_path)
    exact(context["orders"], groups, "Order context coverage")
    exact(context["transactions"], transactions, "Transaction context coverage")
    ns = lambda kind, key: f"shopify:{store}:{kind}:{key}"
    batch = {"orders": [], "line_items": [], "payments": []}
    totals, order_dates = {}, {}
    for oid, rows in groups.items():
        head = rows[0]
        require(
            head["Financial Status"] == "paid", "Only paid, unrefunded orders supported"
        )
        require(head["Currency"] == "INR", "Only INR supported")
        require(not head["Cancelled at"], "Cancelled orders unsupported")
        for field in ["Shipping", "Taxes", "Discount Amount", "Refunded Amount"]:
            require(money(head[field]) == 0, field + " must be zero for profile 1")
        for row in rows:
            # Known non-merchandise adjustments must never disappear from the ledger.
            for field in ["Duties", "Tip"]:
                if row.get(field):
                    require(money(row[field]) == 0, field + " unsupported")
        when = stamp(head["Created at"], timezone)
        require(when <= cutoff, "Order beyond observation cutoff")
        meta = context["orders"][oid]
        exact(
            meta,
            ["customer_id", "channel", "shipping_cost", "unit_costs"],
            "Order metadata",
        )
        skus = [text(r["Lineitem sku"]) for r in rows]
        require(
            len(skus) == len(set(skus)),
            "Repeated SKU within order: native CSV lacks stable line IDs",
        )
        exact(meta["unit_costs"], skus, "Historical unit cost coverage")
        batch["orders"].append(
            [
                ns("order", oid),
                ns("customer", text(meta["customer_id"])),
                when,
                text(meta["channel"]),
                money(meta["shipping_cost"]),
                "INR",
            ]
        )
        gross = 0
        for row, sku in zip(rows, skus):
            require(
                re.fullmatch(r"[1-9]\d*", row["Lineitem quantity"]) is not None,
                "Invalid quantity",
            )
            qty = int(row["Lineitem quantity"])
            require(qty <= 10000, "Quantity exceeds supported range")
            price = money(row["Lineitem price"])
            require(money(row["Lineitem discount"]) == 0, "Line discounts unsupported")
            require(
                row.get("Lineitem fulfillment status", "") != "removed",
                "Removed lines unsupported",
            )
            # SKU is an adapter key only; reject duplicate SKUs rather than invent row IDs.
            lid = hashlib.sha256(json.dumps([oid, sku]).encode()).hexdigest()
            batch["line_items"].append(
                [
                    ns("line", lid),
                    ns("order", oid),
                    sku,
                    qty,
                    price,
                    0,
                    money(meta["unit_costs"][sku]),
                ]
            )
            gross += qty * price
        require(
            gross > 0 and gross == money(head["Subtotal"]) == money(head["Total"]),
            "Order totals do not reconcile to complete, undiscounted merchandise lines",
        )
        totals[oid], order_dates[oid] = gross, when
    captured = defaultdict(int)
    ids = set()
    for key, row in transactions.items():
        oid = row["Order"]
        require(
            oid in groups and row["Name"] == groups[oid][0]["Name"],
            "Transaction order/Name mismatch",
        )
        require(row["Currency"] == "INR", "Transaction currency must be INR")
        require(
            row["Kind"] in ("sale", "capture") and row["Status"] == "success",
            "Only successful sale/capture transactions supported; do not silently drop other events",
        )
        when = stamp(row["Created At"], timezone)
        require(
            order_dates[oid] <= when <= cutoff, "Transaction outside order/cutoff dates"
        )
        meta = context["transactions"][key]
        exact(meta, ["transaction_id", "fee", "reference"], "Transaction metadata")
        require(
            meta["reference"] == row,
            "Transaction reference changed; regenerate context",
        )
        tid = text(meta["transaction_id"])
        require(tid not in ids, "Duplicate provider transaction ID")
        ids.add(tid)
        amount = money(row["Amount"])
        require(amount > 0, "Capture must be positive")
        batch["payments"].append(
            [
                ns("payment", tid),
                ns("order", oid),
                when,
                "capture",
                "succeeded",
                amount,
                money(meta["fee"]),
            ]
        )
        captured[oid] += amount
    require(
        dict(captured) == totals,
        "Successful captures must exactly reconcile every paid order",
    )
    # Stable order independent of CSV ordering, except required contiguous continuation groups.
    for rows in batch.values():
        rows.sort(key=lambda r: r[0])
    receipt = {
        "adapter": "shopify-csv-profile-1",
        "store": store,
        "timezone": timezone,
        "orders": len(groups),
        "line_items": len(batch["line_items"]),
        "captures": len(transactions),
        "charged_paise": sum(totals.values()),
        "captured_paise": sum(captured.values()),
        "orders_sha256": hashlib.sha256(Path(orders_path).read_bytes()).hexdigest(),
        "transactions_sha256": hashlib.sha256(
            Path(transactions_path).read_bytes()
        ).hexdigest(),
        "context_sha256": hashlib.sha256(
            json.dumps(context, sort_keys=True).encode()
        ).hexdigest(),
        "verification": "Structural reconciliation only; merchant source completeness and supplied costs/IDs are not independently verified.",
    }
    return batch, receipt


def ingest_snapshot(c, batch):
    """Caller holds writer lock. Complete orders cannot silently lose/add lines on re-export."""
    prefix = batch["orders"][0][0].rsplit(":order:", 1)[0] + ":order:"
    require(
        all(
            r[0].startswith(prefix)
            for r in c.execute("select order_id from orders").fetchall()
        ),
        "Database contains a different store/source; use a separate database",
    )
    incoming = defaultdict(set)
    for row in batch["line_items"]:
        incoming[row[1]].add(row[0])
    for oid, lines in incoming.items():
        existing = {
            r[0]
            for r in c.execute(
                "select line_id from line_items where order_id=?", [oid]
            ).fetchall()
        }
        require(
            not existing or existing == lines,
            "Changed order line set: reconstruct and reconcile a fresh database",
        )
    return ingest(c, batch)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--orders", required=True)
    parser.add_argument("--transactions", required=True)
    parser.add_argument(
        "--context",
        required=True,
        help="Local supplementary metadata JSON; prepare creates a blank template",
    )
    parser.add_argument("--database", default="store.duckdb")
    parser.add_argument("--as-of")
    parser.add_argument("--report-dir")
    args = parser.parse_args()
    if args.command == "prepare":
        data = template(args.orders, args.transactions)
        with Path(args.context).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
        print(
            "Created local template. Fill all nulls from verified records; no guessed zero costs."
        )
        return
    require(args.as_of is not None, "--as-of is required for run")
    batch, receipt = convert(
        args.orders,
        args.transactions,
        json.loads(Path(args.context).read_text()),
        args.as_of,
    )
    with database_lock(args.database):
        c = connect(args.database)
        try:
            ingestion = ingest_snapshot(c, batch)
        finally:
            c.close()
        result = transform(args.database, as_of=args.as_of)
        if args.report_dir:
            export_report(args.database, args.report_dir)
    print(
        json.dumps(
            {"source": receipt, "ingestion": ingestion, "transformation": result},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
