"""Single-writer orchestration; watermark commits only after dbt build + tests pass."""

from contextlib import contextmanager
from pathlib import Path
import fcntl, json, os, subprocess, sys, tempfile, time
from .core import connect, COLUMNS

ROOT = Path(__file__).resolve().parents[1]
MODELS = [
    "line_economics",
    "order_economics",
    "monthly",
    "payment_reconciliation",
    "sku_returns",
    "retention",
    "channel_acquisition",
]


@contextmanager
def database_lock(database):
    path = Path(str(database) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another MerchantOps writer is running")
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def transform(database, full_refresh=False, as_of="2026-06-30"):
    # Caller holds database_lock across ingestion and transform. dbt opens its own connection.
    c = connect(database)
    lower, previous_as_of = c.execute(
        "select processed_batch,as_of from pipeline_state where id=1"
    ).fetchone()
    upper = c.execute(
        "select coalesce(max(batch_id),0) from ingestion_batches"
    ).fetchone()[0]
    c.execute("update pipeline_state set ready=false where id=1")
    c.close()
    with tempfile.TemporaryDirectory() as directory:
        command = [
            str(Path(sys.executable).with_name("dbt")),
            "build",
            "--project-dir",
            str(ROOT),
            "--profiles-dir",
            str(ROOT),
            "--target-path",
            str(Path(directory) / "target"),
            "--log-path",
            str(Path(directory) / "logs"),
            "--vars",
            json.dumps({"lower_batch": 0 if full_refresh else lower, "as_of": as_of}),
        ]
        if full_refresh:
            command.append("--full-refresh")
        start = time.perf_counter()
        result = subprocess.run(
            command,
            env={
                **os.environ,
                "MERCHANTOPS_DB": str(Path(database).resolve()),
                "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
            },
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                "dbt failed; watermark unchanged. Retry the same batch.\n"
                + result.stdout[-12000:]
                + result.stderr[-2000:]
            )
        report = json.loads((Path(directory) / "target/run_results.json").read_text())
    c = connect(database)
    c.execute(
        "update pipeline_state set processed_batch=?,as_of=?,ready=true where id=1",
        [upper, as_of],
    )
    c.close()
    return {
        "lower_batch": lower,
        "upper_batch": upper,
        "full_refresh": full_refresh,
        "seconds": time.perf_counter() - start,
        "results": [
            {
                "node": r["unique_id"],
                "status": r["status"],
                "seconds": r["execution_time"],
                "rows_affected": r["adapter_response"].get("rows_affected"),
            }
            for r in report["results"]
        ],
    }


def parse_bundle(path):
    data = json.loads(Path(path).read_text())
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "tables"}
        or data["schema_version"] != 3
    ):
        raise ValueError("Expected schema_version=3 and tables")
    if not isinstance(data["tables"], dict) or set(data["tables"]) - set(COLUMNS):
        raise ValueError("Unknown source table")
    batch = {}
    for table, rows in data["tables"].items():
        if not isinstance(rows, list):
            raise ValueError("Table rows must be a list")
        batch[table] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(COLUMNS[table]):
                raise ValueError(f"{table}: fields must exactly match {COLUMNS[table]}")
            batch[table].append([row[k] for k in COLUMNS[table]])
    return batch


def bundle(batch):
    return {
        "schema_version": 3,
        "tables": {
            table: [dict(zip(COLUMNS[table], row)) for row in rows]
            for table, rows in batch.items()
        },
    }
