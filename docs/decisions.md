# MerchantOps design decisions

## 1. Store facts at their real grain
Orders identify the sale/customer/channel. Items hold quantity and historical price/cost. Payment attempts and refund grants have their own immutable keys. Aggregating each child before joining prevents the classic line-item × payment fan-out. A unit test checks two items and two captures against ₹72.60 hand-calculated contribution.

## 2. Keep revenue, contribution and cash separate
Revenue follows accepted merchandise sale. Refund grants reduce revenue on grant date. Successful payment events affect cash and fees. Cash returned does not reduce revenue twice. Contribution subtracts item COGS, shipping, successful fees and advertising; it excludes overhead, tax, shipping income, inventory recovery and return logistics. It is not net profit.

## 3. Avoid invented product allocations
SKU merchandise contribution subtracts item costs only. Shipping, payment fees and ads remain at their real grain. Allocating them to products would require an explicit policy and can change product rankings; no such policy is silently introduced.

## 4. Immutable source events, explicit rejection
Exact duplicate deliveries create no additional facts or batch sequence. Changed payloads under existing IDs fail. Every financially invalid bundle is rolled back, then retained in a separate quarantine transaction. Unknown fields fail at the JSON boundary. Source updates/deletes require a future versioned adapter, not silent overwrites.

## 5. Incremental by ingestion sequence, not transaction date
New facts receive a monotonically increasing ingestion batch ID. Five dbt models use delete+insert with stable unique keys. Changed source IDs locate affected orders/lines and historical reporting partitions. They recompute those keys from complete source history, so late refunds and historical costs work. Small retention/acquisition summaries fully rebuild because a historical first order can change their membership. This choice prioritizes correctness over claiming everything is incremental.

The supported CLI serializes ingestion and transformation with an advisory lock. The watermark advances only after the entire dbt build and tests pass. A failed run can leave some marts updated; it must not be served/exported until recovery. Retry uses the unchanged watermark and replaces the affected keys idempotently. No multi-writer or globally atomic dbt DAG claim is made.

## 6. Reproducible demo vs store operation
The public demo is an immutable synthetic export; browser controls navigate recorded database outputs. The local CLI imports canonical store bundles into a separate database. Neither mode claims platform API connectivity. A fresh demo build cannot pick up an experimental store database. Version 3 rejects legacy schema rather than risking an implicit data migration.

## 7. Honest benchmark
Run real dbt, including checks, on 100,000 multi-item synthetic orders. Full mode builds once. Incremental mode builds initial history, delta and replay. Compare every final model hash and independent Python ledger totals. Record phases, exact command, counts, code/data/dependency hashes and environment. Largest individual process peak RSS is not simultaneous process-tree memory. These workloads do not establish a speedup or production SLA.

## 8. What must precede production
Choose a target store platform, validate its mapping (including tax, cancellations, currencies and refund lifecycle), implement authenticated incremental extraction with completeness checks, define corrections/deletions, obtain operator reconciliation sign-off and observe real workloads. A generic schema alone cannot prove those integrations.
