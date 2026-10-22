"""Canonical integration CLI; no credentials, store access or network required."""

import argparse, json
from datetime import date
from .core import connect, ingest
from .reporting import export_report
from .pipeline import database_lock, parse_bundle, transform


def main():
    parser = argparse.ArgumentParser(
        description="Validate a canonical store batch, ingest once, build and test changed metrics."
    )
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--input", required=True, help="Canonical v3 JSON bundle")
    parser.add_argument("--database", default="store.duckdb")
    parser.add_argument(
        "--as-of", required=True, help="Retention observation end, YYYY-MM-DD"
    )
    parser.add_argument("--full-refresh", action="store_true")
    parser.add_argument(
        "--report-dir",
        help="Write local CSV summaries and metrics after successful checks",
    )
    args = parser.parse_args()
    date.fromisoformat(args.as_of)
    with database_lock(args.database):
        batch = parse_bundle(args.input)
        c = connect(args.database)
        try:
            receipt = ingest(c, batch)
        finally:
            c.close()
        result = transform(args.database, args.full_refresh, args.as_of)
        if args.report_dir:
            export_report(args.database, args.report_dir)
    print(json.dumps({"ingestion": receipt, "transformation": result}, indent=2))


if __name__ == "__main__":
    main()
