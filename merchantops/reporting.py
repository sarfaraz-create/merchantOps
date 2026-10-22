"""Local reports for store imports. Never published by the demo build."""

from pathlib import Path
import json, csv, tempfile, os
import duckdb

REPORT_MODELS = [
    "monthly",
    "sku_returns",
    "retention",
    "channel_acquisition",
    "payment_reconciliation",
]


def export_report(database, directory):
    c = duckdb.connect(str(database), read_only=True)
    try:
        processed, as_of, ready = c.execute(
            "select processed_batch,as_of,ready from pipeline_state where id=1"
        ).fetchone()
        latest = c.execute(
            "select coalesce(max(batch_id),0) from ingestion_batches"
        ).fetchone()[0]
        if processed != latest or not ready:
            raise ValueError(
                "Unprocessed source events: reports require a successful dbt run"
            )
        # Query everything before touching the destination. A missing/invalid mart fails closed.
        tables = {}
        for name in REPORT_MODELS:
            cur = c.execute(f"select * from {name} order by all")
            tables[name] = ([v[0] for v in cur.description], cur.fetchall())
        values = c.execute(
            "select coalesce(sum(net_revenue),0),coalesce(sum(contribution),0) from monthly"
        ).fetchone()
        cash = c.execute(
            "select coalesce(sum(collection_gap),0),coalesce(sum(refund_payable),0) from payment_reconciliation"
        ).fetchone()
    finally:
        c.close()
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "provenance": "User-supplied canonical input; not independently verified",
        "currency": "INR",
        "unit": "paise",
        "processed_batch": processed,
        "retention_as_of": str(as_of),
        "net_revenue": values[0],
        "contribution": values[1],
        "collection_gap": cash[0],
        "refund_payable": cash[1],
        "note": "Local report only. Tax/FX/corrections are unsupported. Do not publish store records without authorization.",
    }
    with tempfile.TemporaryDirectory(dir=out) as temporary:
        tmp = Path(temporary)
        for name, (fields, rows) in tables.items():
            with (tmp / f"{name}.csv").open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(fields)
                writer.writerows(rows)
        (tmp / "summary.json").write_text(json.dumps(summary, indent=2))
        for file in tmp.iterdir():
            os.replace(file, out / file.name)
    return summary
