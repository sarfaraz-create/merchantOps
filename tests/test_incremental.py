"""Exercise real dbt, not a mock of incremental SQL."""

import hashlib, json, subprocess
from pathlib import Path
import pytest
from merchantops.core import connect, ingest, records
from merchantops.evidence import fixture
from merchantops.pipeline import transform, MODELS, parse_bundle, bundle, database_lock


def fingerprint(path):
    c = connect(path)
    result = {n: records(c, f"select * from {n} order by all") for n in MODELS}
    c.close()
    return result


def add(path, batch):
    c = connect(path)
    r = ingest(c, batch)
    c.close()
    return r


def test_real_dbt_late_data_replay_and_full_refresh_equivalence(tmp_path):
    db = tmp_path / "incremental.duckdb"
    full = tmp_path / "full.duckdb"
    b = fixture()
    # Add a later month so historical deltas cannot pass a max(event_date) filter by accident.
    b["spend"] = [["later", "2026-06-01", "Paid social", 100]]
    add(db, b)
    first = transform(db)
    before = fingerprint(db)
    delta = {
        "refunds": [["r", "l1", "2026-02-04", 2000]],
        "payments": [["p3", "demo", "2026-02-05", "refund", "succeeded", 2000, 10]],
        "spend": [["old", "2026-01-02", "Paid social", 500]],
    }
    add(db, delta)
    report = transform(db)
    after = fingerprint(db)
    from merchantops.reporting import export_report

    summary = export_report(db, tmp_path / "reports")
    assert summary["contribution"] == 4650
    assert summary["refund_payable"] == 0
    assert (tmp_path / "reports/monthly.csv").exists()
    c = connect(db)
    c.execute("update pipeline_state set ready=false where id=1")
    c.close()
    with pytest.raises(ValueError, match="successful dbt"):
        export_report(db, tmp_path / "blocked-report")
    c = connect(db)
    c.execute("update pipeline_state set ready=true where id=1")
    c.close()

    assert report["lower_batch"] == 1 and report["upper_batch"] == 2
    assert after["monthly"][0]["contribution"] == 6760
    assert after["monthly"][1]["contribution"] == -2010
    assert after["monthly"][-1] == before["monthly"][-1]
    assert after["payment_reconciliation"][0]["refund_payable"] == 0
    assert add(db, delta)["inserted_rows"] == 0
    transform(db)
    assert fingerprint(db) == after
    for path in [full]:
        add(path, b)
        add(path, delta)
        transform(path, full_refresh=True)
    assert fingerprint(full) == after
    # A historical first purchase must move acquisition/cohort summaries correctly.
    backfill = {
        "orders": [["ancient", "customer", "2025-12-01", "Organic", 0, "INR"]],
        "line_items": [["ancient-line", "ancient", "Tee", 1, 1000, 0, 400]],
    }
    add(db, backfill)
    transform(db)
    add(full, backfill)
    transform(full, full_refresh=True)
    assert fingerprint(full) == fingerprint(db)
    assert (
        next(
            r
            for r in fingerprint(db)["channel_acquisition"]
            if r["channel"] == "Organic"
        )["first_customers"]
        == 1
    )

    # A later distinct line expands an existing order; it must not multiply earlier payments.
    late_line = {"line_items": [["late-item", "demo", "Bag", 1, 1000, 0, 400]]}
    add(db, late_line)
    transform(db)
    add(full, late_line)
    transform(full, full_refresh=True)
    assert fingerprint(full) == fingerprint(db)
    cash = next(
        r for r in fingerprint(db)["payment_reconciliation"] if r["order_id"] == "demo"
    )
    assert cash["collection_gap"] == 1000 and cash["captured"] == 12000


def test_failed_dbt_run_does_not_advance_watermark(tmp_path, monkeypatch):
    db = tmp_path / "failed.duckdb"
    add(db, fixture())

    def fail(*args, **kwargs):
        return subprocess.CompletedProcess([], 1, "injected failure", "")

    monkeypatch.setattr("merchantops.pipeline.subprocess.run", fail)
    with pytest.raises(RuntimeError, match="watermark unchanged"):
        transform(db)
    c = connect(db)
    assert c.execute("select processed_batch from pipeline_state").fetchone()[0] == 0
    c.close()


def test_nested_writer_refused(tmp_path):
    db = tmp_path / "locked.duckdb"
    with database_lock(db):
        with pytest.raises(RuntimeError, match="Another"):
            with database_lock(db):
                pass


def test_named_integration_contract(tmp_path):
    path = tmp_path / "batch.json"
    data = bundle(fixture())
    path.write_text(json.dumps(data))
    assert parse_bundle(path) == fixture()
    data["tables"]["line_items"][0]["unexpected"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="exactly match"):
        parse_bundle(path)


def test_report_refuses_unprocessed_input(tmp_path):
    from merchantops.reporting import export_report

    db = tmp_path / "unprocessed.duckdb"
    add(db, fixture())
    with pytest.raises(ValueError, match="Unprocessed"):
        export_report(db, tmp_path / "reports")
    assert not (tmp_path / "reports").exists()
