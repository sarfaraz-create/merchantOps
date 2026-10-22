from pathlib import Path
import json, sys, time, hashlib, platform, tempfile, shutil
from datetime import datetime, timezone
from .core import connect, ingest, synthetic, records
from .pipeline import transform, database_lock
from .evidence import replay_evidence
from .publishing import decision_memo, export_memo


def main():
    start = time.perf_counter()
    batch = synthetic()
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "merchantops-v3.duckdb"
        with database_lock(db):
            c = connect(db)
            ingest(c, batch)
            ingest(c, batch)
            c.close()
            report = transform(db, full_refresh=True)
        c = connect(db)
        payload = {
            "provenance": "Synthetic data, seed 42; no merchant results.",
            "as_of": "2026-06-30",
            "monthly": records(c, "select * from monthly order by month,channel"),
            "retention": records(c, "select * from retention order by cohort"),
            "products": records(
                c, "select * from sku_returns order by channel,product"
            ),
            "acquisition": records(
                c, "select * from channel_acquisition order by channel"
            ),
            "payments": records(
                c,
                "select channel,count(*)::bigint as orders,sum(captured)::bigint as captured,sum(returned)::bigint as returned,sum(collection_gap)::bigint as collection_gap,sum(refund_payable)::bigint as refund_payable,sum(failed_attempts)::bigint as failed_attempts from payment_reconciliation group by channel order by channel",
            ),
            "payment_exceptions": records(
                c,
                "select * from payment_reconciliation where collection_gap>0 or refund_payable>0 order by order_id limit 10",
            ),
            "sql": {f.stem: f.read_text() for f in Path("models").glob("*.sql")},
        }
        counts = {
            k: c.execute(f"select count(*) from {k}").fetchone()[0] for k in batch
        }
        c.close()
        shutil.copyfile(db, "merchantops-v3.duckdb")
    payload["memo"] = decision_memo(payload)
    export_memo(payload["memo"])
    payload["replay"] = replay_evidence()
    payload["measurement"] = {
        "rows": counts,
        "build_seconds": round(time.perf_counter() - start, 3),
        "python": platform.python_version(),
        "source_sha256": hashlib.sha256(
            json.dumps(batch, sort_keys=True).encode()
        ).hexdigest(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dbt": report,
    }
    Path("dist").mkdir(exist_ok=True)
    Path("dist/data.json").write_text(json.dumps(payload, default=str, indent=2))
    Path("docs/results.json").write_text(json.dumps(payload["measurement"], indent=2))
    Path("docs/source-manifest.json").write_text(
        json.dumps(
            {
                "dataset": "Synthetic store v3",
                "seed": 42,
                "period": ["2026-01-01", "2026-06-30"],
                "tables": counts,
                "source_sha256": payload["measurement"]["source_sha256"],
                "currency": "INR",
                "monetary_unit": "paise",
                "source": "merchantops.core.synthetic",
            },
            indent=2,
        )
    )
    print(
        json.dumps(
            {
                "counts": counts,
                "build_seconds": payload["measurement"]["build_seconds"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
