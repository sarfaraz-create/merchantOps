"""Synthetic fixtures shaped from Shopify's documented CSV contracts, not real exports."""

import csv
import json
import subprocess
import sys
from pathlib import Path
import pytest
from merchantops.core import connect
from merchantops.shopify import (
    convert,
    ingest_snapshot,
    template,
    money,
    transaction_key,
)
from merchantops.pipeline import transform, MODELS
from merchantops.reporting import export_report

FIXTURES = Path(__file__).resolve().parents[1] / "examples/shopify"


@pytest.fixture
def source(tmp_path):
    for name in ["orders.csv", "transactions.csv", "context.json"]:
        (tmp_path / name).write_bytes((FIXTURES / name).read_bytes())
    return tmp_path


def context(source):
    return json.loads((source / "context.json").read_text())


def convert_source(source):
    return convert(
        source / "orders.csv",
        source / "transactions.csv",
        context(source),
        "2026-06-30",
    )


def edit(source, filename, fn):
    p = source / filename
    with p.open(newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    fn(rows)
    with p.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def refresh_context(source):
    old = context(source)
    fresh = template(source / "orders.csv", source / "transactions.csv")
    for i, m in enumerate(fresh["transactions"].values()):
        m.update(transaction_id=f"tx-{i}", fee="1.00")
    old["transactions"] = fresh["transactions"]
    (source / "context.json").write_text(json.dumps(old))


def test_hand_calculated_mapping_and_pii_exclusion(source):
    b, r = convert_source(source)
    assert (
        len(b["orders"]) == 1 and len(b["line_items"]) == 2 and len(b["payments"]) == 2
    )
    assert b["orders"][0][2] == "2026-02-01"  # timezone crosses month boundary
    assert sum(l[3] * l[4] for l in b["line_items"]) == 13000
    assert sum(l[3] * l[6] for l in b["line_items"]) == 4000
    assert sum(p[6] for p in b["payments"]) == 260
    assert r["charged_paise"] == r["captured_paise"] == 13000
    assert "synthetic-provider" not in json.dumps(
        b
    )  # no unnecessary provider/PII fields


@pytest.mark.parametrize(
    "field,value",
    [
        ("Financial Status", "partially_refunded"),
        ("Currency", "USD"),
        ("Cancelled at", "2026-02-02"),
        ("Taxes", "1.00"),
        ("Shipping", "1.00"),
        ("Discount Amount", "1.00"),
        ("Refunded Amount", "1.00"),
        ("Lineitem discount", "1.00"),
        ("Subtotal", "129.00"),
        ("Total", "131.00"),
        ("Lineitem quantity", "1.5"),
        ("Lineitem price", "NaN"),
        ("Lineitem sku", ""),
        ("Created at", "2026-01-31 12:00:00"),
        ("Created at", "2027-01-01T00:00:00Z"),
    ],
)
def test_unsupported_orders_fail_closed(source, field, value):
    edit(source, "orders.csv", lambda rows: rows[0].update({field: value}))
    with pytest.raises(ValueError):
        convert_source(source)


@pytest.mark.parametrize(
    "field,value",
    [
        ("Kind", "refund"),
        ("Kind", "authorization"),
        ("Status", "pending"),
        ("Status", "failure"),
        ("Currency", "USD"),
        ("Order", "9999"),
        ("Name", "#other"),
        ("Amount", "79.99"),
        ("Created At", "2025-01-01T00:00:00Z"),
        ("Created At", "2027-01-01T00:00:00Z"),
    ],
)
def test_transactions_not_inferred_or_silently_dropped(source, field, value):
    edit(source, "transactions.csv", lambda rows: rows[0].update({field: value}))
    refresh_context(source)
    with pytest.raises(ValueError):
        convert_source(source)


def test_duplicate_sku_and_ambiguous_transactions_rejected(source):
    edit(source, "orders.csv", lambda rows: rows[1].update({"Lineitem sku": "TEE"}))
    with pytest.raises(ValueError, match="Repeated SKU"):
        convert_source(source)
    edit(source, "transactions.csv", lambda rows: rows.append(rows[0].copy()))
    with pytest.raises(ValueError, match="Indistinguishable"):
        convert_source(source)


def test_missing_cost_and_ids_are_not_zero_defaults(source):
    c = context(source)
    c["orders"]["9001"]["shipping_cost"] = None
    with pytest.raises(ValueError):
        convert(source / "orders.csv", source / "transactions.csv", c, "2026-06-30")
    c = context(source)
    c["orders"]["9001"]["unit_costs"].pop("TEE")
    with pytest.raises(ValueError, match="cost coverage"):
        convert(source / "orders.csv", source / "transactions.csv", c, "2026-06-30")
    c = context(source)
    for m in c["transactions"].values():
        m["transaction_id"] = "same"
    with pytest.raises(ValueError, match="Duplicate provider"):
        convert(source / "orders.csv", source / "transactions.csv", c, "2026-06-30")


def test_continuation_boundaries_and_incomplete_orders(source):
    edit(source, "orders.csv", lambda rows: rows[1].update({"Name": "#unknown"}))
    with pytest.raises(ValueError, match="Continuation"):
        convert_source(source)
    edit(source, "orders.csv", lambda rows: rows.pop())
    c = context(source)
    c["orders"]["9001"]["unit_costs"].pop("BAG")
    with pytest.raises(ValueError, match="totals"):
        convert(source / "orders.csv", source / "transactions.csv", c, "2026-06-30")


def test_csv_quoting_bom_and_extra_pii_not_copied(source):
    path = source / "orders.csv"
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    for row in rows:
        row["Email"] = "private@example.test"
        row["Notes"] = "private,\nnotes"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields + ["Email", "Notes"])
        writer.writeheader()
        writer.writerows(rows)
    b, r = convert_source(source)
    assert "private" not in json.dumps([b, r])
    assert b["orders"][0][1].endswith("customer-1")


def test_duplicate_headers_and_bad_row_width(source):
    p = source / "orders.csv"
    p.write_text(p.read_text().replace("Id,", "Id,Id,", 1))
    with pytest.raises(ValueError, match="Duplicate CSV"):
        convert_source(source)


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "-1", "1.001", "1e2", "1,000", 1.0, None]
)
def test_exact_decimal_rejection(value):
    with pytest.raises(ValueError):
        money(value)


def test_reordered_lines_and_transactions_are_same_events(source):
    # Within one order move header data to its new first line, as Shopify would.
    original, _ = convert_source(source)

    def swap(rows):
        fields = [k for k in rows[0] if not k.startswith("Lineitem") and k != "Name"]
        for k in fields:
            rows[0][k], rows[1][k] = rows[1][k], rows[0][k]
        rows.reverse()

    edit(source, "orders.csv", swap)
    edit(source, "transactions.csv", lambda rows: rows.reverse())
    assert convert_source(source)[0] == original


def test_replay_atomic_conflict_and_snapshot_removal_guard(source):
    b, _ = convert_source(source)
    c = connect()
    try:
        assert ingest_snapshot(c, b)["inserted_rows"] == 5
        assert ingest_snapshot(c, b)["inserted_rows"] == 0
        changed = json.loads(json.dumps(b))
        changed["line_items"][0][6] += 1
        with pytest.raises(ValueError, match="Conflicting"):
            ingest_snapshot(c, changed)
        assert (
            c.execute("select sum(unit_cost*quantity) from line_items").fetchone()[0]
            == 4000
        )
        changed = json.loads(json.dumps(b))
        changed["line_items"].pop()
        with pytest.raises(ValueError, match="Changed order line set"):
            ingest_snapshot(c, changed)
        changed = json.loads(json.dumps(b))
        changed["orders"][0][0] = "shopify:other:order:9001"
        with pytest.raises(ValueError, match="different store"):
            ingest_snapshot(c, changed)
    finally:
        c.close()


def test_cli_real_dbt_reports_replay_and_full_equivalence(source):
    db = source / "shopify.duckdb"
    report = source / "reports"
    command = [
        sys.executable,
        "-m",
        "merchantops.shopify",
        "run",
        "--orders",
        str(source / "orders.csv"),
        "--transactions",
        str(source / "transactions.csv"),
        "--context",
        str(source / "context.json"),
        "--database",
        str(db),
        "--as-of",
        "2026-06-30",
        "--report-dir",
        str(report),
    ]
    first = json.loads(subprocess.check_output(command, text=True))
    assert first["ingestion"]["inserted_rows"] == 5
    summary = json.loads((report / "summary.json").read_text())
    assert summary["contribution"] == 8240 and summary["refund_payable"] == 0
    c = connect(db)
    before = {
        m: c.execute(f"select * from {m} order by all").fetchall() for m in MODELS
    }
    c.close()
    second = json.loads(subprocess.check_output(command, text=True))
    assert second["ingestion"]["inserted_rows"] == 0
    transform(db, full_refresh=True)
    c = connect(db)
    assert {
        m: c.execute(f"select * from {m} order by all").fetchall() for m in MODELS
    } == before
    c.close()


def test_prepare_never_overwrites_existing_context(source):
    command = [
        sys.executable,
        "-m",
        "merchantops.shopify",
        "prepare",
        "--orders",
        str(source / "orders.csv"),
        "--transactions",
        str(source / "transactions.csv"),
        "--context",
        str(source / "context.json"),
    ]
    before = (source / "context.json").read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert (source / "context.json").read_bytes() == before


def test_alias_headers_and_bad_width(source):
    p = source / "orders.csv"
    original = p.read_text()
    p.write_text(
        original.replace("Lineitem sku", "Lineitem SKU").replace(
            "Cancelled at", "Canceled at"
        )
    )
    assert convert_source(source)[1]["orders"] == 1
    p.write_text(original + "broken,row\n")
    with pytest.raises(ValueError, match="row width"):
        convert_source(source)


def test_prepare_new_template_has_no_invented_costs(source):
    data = template(source / "orders.csv", source / "transactions.csv")
    assert data["store"] is None and data["timezone"] is None
    assert data["orders"]["9001"]["shipping_cost"] is None
    assert all(
        x["fee"] is None and x["transaction_id"] is None
        for x in data["transactions"].values()
    )


def test_new_complete_order_incremental_keeps_old_order(source):
    db = source / "delta.duckdb"
    b, _ = convert_source(source)
    c = connect(db)
    ingest_snapshot(c, b)
    c.close()
    transform(db)
    # A second export with one new complete order for the same customer.
    edit(
        source,
        "orders.csv",
        lambda rows: [
            r.update(
                {
                    "Name": "#1002",
                    **(
                        {"Id": "9002", "Created at": "2026-02-10T12:00:00+05:30"}
                        if i == 0
                        else {}
                    ),
                }
            )
            for i, r in enumerate(rows)
        ],
    )
    edit(
        source,
        "transactions.csv",
        lambda rows: [
            r.update(
                {
                    "Order": "9002",
                    "Name": "#1002",
                    "Created At": f"2026-02-10T12:0{i+1}:00+05:30",
                }
            )
            for i, r in enumerate(rows)
        ],
    )
    cxt = context(source)
    cxt["orders"]["9002"] = cxt["orders"].pop("9001")
    (source / "context.json").write_text(json.dumps(cxt))
    refresh_context(source)
    b, _ = convert_source(source)
    c = connect(db)
    assert ingest_snapshot(c, b)["inserted_rows"] == 5
    c.close()
    result = transform(db)
    assert result["lower_batch"] == 1 and result["upper_batch"] == 2
    c = connect(db)
    before = {
        m: c.execute(f"select * from {m} order by all").fetchall() for m in MODELS
    }
    assert c.execute("select count(*) from orders").fetchone()[0] == 2
    assert (
        c.execute("select sum(contribution) from monthly").fetchone()[0] == 16540
    )  # second fee total 2.00
    assert c.execute("select retention_30d from retention").fetchone()[0] == 1.0
    c.close()
    transform(db, full_refresh=True)
    c = connect(db)
    assert {
        m: c.execute(f"select * from {m} order by all").fetchall() for m in MODELS
    } == before
    c.close()
