"""Re-run only checked-in synthetic Shopify-shaped fixtures for the public build."""

import json
import tempfile
from pathlib import Path
from .core import connect
from .pipeline import transform
from .reporting import export_report
from .shopify import convert, ingest_snapshot


def example_evidence():
    root = Path(__file__).resolve().parents[1]
    source = root / "examples/shopify"
    batch, receipt = convert(
        source / "orders.csv",
        source / "transactions.csv",
        json.loads((source / "context.json").read_text()),
        "2026-06-30",
    )
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "example.duckdb"
        c = connect(db)
        first = ingest_snapshot(c, batch)
        replay = ingest_snapshot(c, batch)
        c.close()
        result = transform(db)
        summary = export_report(db, Path(directory) / "reports")
    if summary["contribution"] != 8240 or replay["inserted_rows"] != 0:
        raise RuntimeError("Shopify fixture does not match hand calculation")
    return {
        "provenance": "Synthetic Shopify-shaped CSV fixtures, not an export from a real merchant. No live connection.",
        "source": receipt,
        "first_inserted_rows": first["inserted_rows"],
        "replay_inserted_rows": replay["inserted_rows"],
        "summary": summary,
        "dbt_results": result["results"],
    }
