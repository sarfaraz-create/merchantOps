"""Real dbt full-refresh vs incremental correctness and cost; no speedup claim."""

import argparse, hashlib, json, platform, resource, subprocess, sys, time, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from .core import connect, ingest, synthetic
from .pipeline import transform, MODELS


def workload(n):
    base = synthetic()
    out = {k: [] for k in base}
    remaining = n
    block = 0
    while remaining:
        prefix = f"{block}-"
        selected = base["orders"][:remaining]
        oids = {r[0] for r in selected}
        lines = [r for r in base["line_items"] if r[1] in oids]
        lids = {r[0] for r in lines}
        for table, rows in base.items():
            for row in rows:
                if table == "orders" and row[0] not in oids:
                    continue
                if table in ("line_items", "payments") and row[1] not in oids:
                    continue
                if table == "refunds" and row[1] not in lids:
                    continue
                r = list(row)
                r[0] = prefix + r[0]
                if table in ("orders", "line_items", "payments", "refunds"):
                    r[1] = prefix + r[1]
                out[table].append(r)
        remaining -= len(selected)
        block += 1
    return out


def split(batch):
    before = {}
    delta = {}
    old_orders = {r[0] for r in batch["orders"] if r[2] < "2026-04-01"}
    for table, rows in batch.items():
        predicate = (
            (lambda r: r[1] in old_orders)
            if table == "line_items"
            else (lambda r: r[1 if table == "spend" else 2] < "2026-04-01")
        )
        before[table] = [r for r in rows if predicate(r)]
        delta[table] = [r for r in rows if not predicate(r)]
    return before, delta


def fingerprint(c):
    return {
        name: hashlib.sha256(
            json.dumps(
                c.execute(f"select * from {name} order by all").fetchall(), default=str
            ).encode()
        ).hexdigest()
        for name in MODELS
    }


def measure(mode, n):
    start = time.perf_counter()
    batch = workload(n)
    phases = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "benchmark.duckdb"

        def run(label, b, full=False):
            t = time.perf_counter()
            c = connect(path)
            receipt = ingest(c, b)
            c.close()
            ingestion = time.perf_counter() - t
            report = transform(path, full_refresh=full)
            phases.append(
                {
                    "phase": label,
                    "ingest_seconds": ingestion,
                    "ingestion": receipt,
                    "dbt": report,
                }
            )

        if mode == "full":
            run("full", batch, True)
        else:
            before, delta = split(batch)
            run("initial", before)
            run("delta", delta)
            c = connect(path)
            old = fingerprint(c)
            c.close()
            run("replay", delta)
            c = connect(path)
            assert fingerprint(c) == old, "Replay changed financial outputs"
            c.close()
        c = connect(path)
        expected = (
            sum(l[3] * (l[4] - l[6]) - l[5] for l in batch["line_items"])
            - sum(o[4] for o in batch["orders"])
            - sum(r[3] for r in batch["refunds"])
            - sum(p[6] for p in batch["payments"] if p[4] == "succeeded")
            - sum(s[3] for s in batch["spend"])
        )
        actual = c.execute("select sum(contribution) from monthly").fetchone()[0]
        assert expected == actual, "Independent ledger mismatch"
        counts = {
            k: c.execute(f"select count(*) from {k}").fetchone()[0] for k in batch
        }
        assert counts == {k: len(v) for k, v in batch.items()}
        hashes = fingerprint(c)
        c.close()
    scale = 1024**2 if sys.platform == "darwin" else 1024
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / scale
    child = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / scale
    return {
        "mode": mode,
        "rows": counts,
        "source_sha256": hashlib.sha256(
            json.dumps(batch, sort_keys=True).encode()
        ).hexdigest(),
        "phases": phases,
        "wall_seconds": time.perf_counter() - start,
        "worker_peak_rss_mib": own,
        "largest_child_peak_rss_mib": child,
        "peak_rss_mib": max(own, child),
        "output_sha256": hashes,
        "contribution_paise": actual,
        "independent_reconciliation": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--orders", type=int, default=100000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--worker", choices=["full", "incremental"])
    args = parser.parse_args()
    if args.orders < 1 or args.repeats < 1:
        parser.error("Counts must be positive")
    if args.worker:
        print(json.dumps(measure(args.worker, args.orders)))
        return
    runs = []
    for repeat in range(args.repeats):
        for mode in ["full", "incremental"]:
            r = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "merchantops.benchmark",
                    "--orders",
                    str(args.orders),
                    "--worker",
                    mode,
                ],
                capture_output=True,
                text=True,
            )
            if r.returncode:
                raise RuntimeError(r.stdout + r.stderr)
            runs.append({"repeat": repeat + 1, **json.loads(r.stdout)})
    equal = all(
        r["output_sha256"] == runs[0]["output_sha256"]
        and r["source_sha256"] == runs[0]["source_sha256"]
        for r in runs
    )
    assert equal, "Full and incremental results differ"
    files = sorted(
        [
            *Path("merchantops").glob("*.py"),
            *Path("models").glob("*.sql"),
            *Path("macros").glob("*.sql"),
            Path("requirements.txt"),
        ]
    )
    git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    result = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": f"python -m merchantops.benchmark --orders {args.orders} --repeats {args.repeats}",
        "machine": {
            "os": platform.platform(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
            "duckdb_threads": 1,
        },
        "code_sha256": hashlib.sha256(
            b"".join(str(f).encode() + f.read_bytes() for f in files)
        ).hexdigest(),
        "dependency_sha256": hashlib.sha256(
            Path("requirements.txt").read_bytes()
        ).hexdigest(),
        "git_base_commit": git.stdout.strip() if git.returncode == 0 else None,
        "scope": "Actual dbt build including tests. Five incremental models use affected keys/partitions; retention and acquisition rebuild. Full mode: one build. Incremental mode: initial, delta and replay builds. Largest individual process peak RSS is NOT aggregate memory. Wall time includes generation, checks and hashing. No speedup claim.",
        "workload": "Seed 42 multi-item store replicated with disjoint IDs and truncated to N orders; includes split/failed payments and refund liabilities. Spend is replicated per block.",
        "outputs_equal": equal,
        "runs": runs,
    }
    for path in ["docs/benchmark.json", "dist/benchmark.json"]:
        Path(path).write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                "outputs_equal": equal,
                "runs": [
                    {k: r[k] for k in ["mode", "wall_seconds", "peak_rss_mib", "rows"]}
                    for r in runs
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
