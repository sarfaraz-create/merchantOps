# Verification — 23 October 2026 (Asia/Kolkata)

Version 3 verifies normalized source grains and actual incremental dbt, not a simulated incremental query path.

- Hand-calculated two-item/two-capture fixture; partial line refund; delayed cash return; failed and partial captures; cumulative over-refunds; temporal cash/refund bounds; whole-batch rollback; duplicates; conflicts; schema/currency validation; quoted multiline values; zero-revenue/spend-only month; SKU and acquisition denominators; retention boundaries.
- Real dbt integration test: old refund and backdated spend after a newer month, duplicate replay, historical first purchase and equality against an independent full refresh across all seven models.
- Failure-injection test: failed dbt command does not advance the successful watermark. Concurrent supported writers are refused.
- 100,000-order benchmark uses actual dbt builds and checks, three fresh processes per mode. Individual phase results, data/code hashes, counts, environment and peak-memory semantics are recorded in benchmark.json. No production throughput or speedup claim.
- Public browser shows a static synthetic snapshot; replay controls display recorded DuckDB/dbt output. They do not mutate a hosted warehouse.

The previous v2 CSV detection bug remains covered by a quoted/multiline regression. Version 3 rejects the legacy database schema and creates a distinct demo database path. GitHub run status should be read from the repository's Actions page; this document does not imply a run passed merely because its workflow exists.

## Shopify CSV profile 1

Synthetic fixtures use documented Orders and transaction-history headers. Tests cover complete multi-line grouping, split captures, source reconciliation, exact decimals, timezone month rollover, unknown costs/IDs, CSV quoting/BOM, PII exclusion, replay, changed snapshot rejection and unsupported lifecycle events. The CLI test runs actual dbt, exports a hand-calculated ₹82.40 contribution report, and compares all seven models after full refresh. The public build separately executes this example and records its receipt in `dist/shopify-example.json`.

This evidence does not verify a real export, live Shopify connection, all export variants or the truth of externally supplied costs/customer/payment IDs. The scale benchmark continues to exercise synthetic canonical records, not CSV parsing at scale.
