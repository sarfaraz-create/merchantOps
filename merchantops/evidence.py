"""Actual database traces, generated locally. The hosted demo replays these records."""

from .core import connect, ingest, records
from .pipeline import transform
from pathlib import Path
import tempfile


def fixture():
    return {
        "orders": [["demo", "customer", "2026-01-01", "Paid social", 500, "INR"]],
        "line_items": [
            ["l1", "demo", "Tee", 2, 5000, 1000, 1500],
            ["l2", "demo", "Cap", 1, 3000, 0, 1000],
        ],
        "payments": [
            ["p1", "demo", "2026-01-01", "capture", "succeeded", 7000, 140],
            ["p2", "demo", "2026-01-01", "capture", "succeeded", 5000, 100],
        ],
    }


def replay_evidence():
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "trace.duckdb"
        stages = []
        batches = [
            ("Two lines, split payment", fixture()),
            (
                "Late partial line refund",
                {"refunds": [["r1", "l1", "2026-02-04", 2000]]},
            ),
            ("Identical replay", {"refunds": [["r1", "l1", "2026-02-04", 2000]]}),
            (
                "Refund cash returned + campaign cost",
                {
                    "payments": [
                        ["p3", "demo", "2026-02-05", "refund", "succeeded", 2000, 0]
                    ],
                    "spend": [["ad", "2026-02-05", "Paid social", 1000]],
                },
            ),
            (
                "Invalid line reference quarantined",
                {"refunds": [["bad", "unknown", "2026-02-06", 100]]},
            ),
        ]
        for name, batch in batches:
            c = connect(db)
            try:
                receipt = ingest(c, batch)
            except ValueError as error:
                receipt = {"rejected": str(error)}
            finally:
                c.close()
            report = transform(db)
            c = connect(db)
            stage = {
                "name": name,
                "monthly": records(
                    c, "select month,contribution from monthly order by month"
                ),
                **{
                    table: c.execute(f"select count(*) from {table}").fetchone()[0]
                    for table in ["orders", "line_items", "payments", "refunds"]
                },
                "quarantined_batches": c.execute(
                    "select count(*) from quarantine"
                ).fetchone()[0],
                "reconciliation": records(c, "select * from payment_reconciliation")[0],
                "ingestion": receipt,
                "watermark": [report["lower_batch"], report["upper_batch"]],
            }
            if "rejected" in receipt:
                stage["rejection"] = {"reason": receipt["rejected"]}
            stages.append(stage)
            c.close()
    return {
        "kind": "Actual DuckDB + dbt executions recorded at build time; browser is read-only",
        "command": "python -m merchantops.build",
        "stages": stages,
    }
