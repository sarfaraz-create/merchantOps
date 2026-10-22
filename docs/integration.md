# Canonical store integration — v3

This importer works on the contract below. It does not fetch Shopify, WooCommerce, Stripe or other platform data. Build and contract-test a platform mapper before claiming that integration.

## Envelope and exact fields
Use UTF-8 JSON: `{"schema_version":3,"tables":{"orders":[...],"line_items":[...]}}`. Tables can be omitted for later event batches. Each record is an object whose keys must match the relevant list exactly. Example files are executable inputs.

| Table | Exact fields | Grain |
|---|---|---|
| orders | order_id, customer_id, ordered_at, channel, shipping, currency | Accepted sale; at least one initial line required |
| line_items | line_id, order_id, product, quantity, unit_price, discount, unit_cost | One original order line; discount is a LINE TOTAL |
| payments | payment_id, order_id, occurred_at, kind, status, amount, fee | Immutable terminal attempt/event; kind capture/refund; status succeeded/failed |
| refunds | refund_id, line_id, refunded_at, amount | Granted partial/full credit against an original line |
| spend | spend_id, spent_at, channel, amount | Immutable channel cost event |

IDs and dimensions are nonempty strings. Currency must be INR. Dates are ISO YYYY-MM-DD in one consistent store timezone. Money is nonnegative integer paise, not float rupees; individual monetary inputs are limited to 10^12 paise. Quantity is an integer from 1 to 10,000. Unit price/cost × quantity produces line totals; discount cannot exceed gross line value. Refunds cumulatively cannot exceed a line's charged amount. Financial aggregates use bigint; extreme aggregate overflow fails rather than silently rounding.

Payment captures cannot exceed total merchandise charged. Successful refund cash cannot exceed captured cash or granted refunds, including cumulative calendar-day balances. Same-day event ordering is not represented. A failed event has zero fee and no cash effect. A later success needs its own immutable event ID; do not overwrite a prior failed attempt. Fees from successful capture and refund events are costs; fee credits are unsupported.

## Mapping rules before a real import
1. Filter to accepted sales; do not import carts, authorizations, draft/cancelled orders as completed revenue. Revenue is merchandise sale date, not settlement date.
2. Preserve stable platform IDs. Namespace IDs by source if several systems contribute. One database is one store; mixing stores is unsupported.
3. Convert exact decimal currency using the currency's minor-unit rule; only INR is accepted here. Reject unknown currency and costs. Do not insert zeros as guesses.
4. Supply historical item cost and actual shipping cost, not shipping income. Tax, shipping income and discounts need explicit separation upstream. Order discount allocation across lines must be exact and documented by your mapper.
5. Map partial credits to original lines, preserving total amount. Keep refund-grant events separate from provider cash-return events. A delayed return remains refund payable.
6. Reconcile source order/line counts, charge totals and date coverage. Record extract IDs, completeness and known exclusions. Current CLI does not verify platform pagination or extract freshness.

## Operation
```sh
python -m merchantops run --input export.json --database store.duckdb --as-of 2026-06-30 --report-dir store-reports
```
`as-of` is the retention observation boundary, not a filter on the entire financial ledger. Only load events within the intended report snapshot. The command takes an advisory single-writer lock, validates, ingests atomically, runs dbt and tests, and advances the successful watermark. The JSON receipt shows inserted rows and processing bounds. `--report-dir` writes local financial/SKU/retention/acquisition/payment CSV tables and summary.json only after the successful run. It does not change or publish the demo. Replaying the same input is safe.

For an independent reference rebuild, copy the database while no writer is running, then use `--full-refresh` on the copy. The implementation's automated test compares all seven final model outputs this way. Full refresh does not change raw events.

## Failure and recovery
- A rejected financial batch rolls back in full. A separate content-hashed quarantine entry retains the first rejection and original payload. Do not export quarantine data publicly.
- Malformed JSON/envelope/field names fail at the importer boundary before database ingestion; these parser errors are reported to the caller and are not quarantined. Retain source files in your own access-controlled import workflow.
- Orphan events can be resubmitted once their required order/line or granted refund arrives. The old rejection remains as audit evidence.
- dbt failure leaves the watermark unchanged. Some marts may have updated because dbt's entire DAG is not one transaction. Do not serve or export that intermediate database; retry the same bundle until all checks pass.
- Process crash before ingestion commit leaves no financial effect. After ingestion commit but before dbt completion, replay is safe and rebuilds affected keys from the last successful watermark.
- Locking is enforced by the CLI, not by arbitrary external SQL or scripts. Run one writer and do not read during refresh when a consistent cross-model snapshot is required.
- Corrections/deletions, source lifecycle updates and schema migration are not supported. Do not mutate source tables manually and expect incremental models to discover it. Plan a versioned adapter or a validated full reconstruction.

## Data handling
No real store data is uploaded by this CLI; it operates locally. `merchantops.build` creates only the public synthetic dataset. Keep real exports/databases/quarantine outside the repository. Do not add them to GitHub or Sites. Public demo publishing uses an explicit source allowlist.
