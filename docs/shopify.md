# Shopify CSV adapter — profile 1

## What works, and what has actually been verified

`python -m merchantops.shopify` reads Shopify's **Orders CSV** and **transaction-history CSV** locally, joins complete orders to their item rows and captures, requires missing cost/identity metadata, and runs the existing tested incremental dbt pipeline. No credentials or store connection are needed.

Verified: synthetic CSV fixtures based on [Shopify's official export documentation](https://help.shopify.com/en/manual/fulfillment/managing-orders/exporting-orders), consulted 23 October 2026. Tests execute the CLI, DuckDB, dbt and reports, check replay and compare all seven models with a full rebuild. **No merchant-supplied export, Shopify development store, or live API has been tested.** The small fixture is authored here; it is not a download from Shopify. The 100,000-order benchmark measures the canonical pipeline, not this CSV adapter.

## Exact support matrix

| Input | Supported | Rejected or not implemented |
|---|---|---|
| Format | UTF-8/BOM CSV, quoted values/newlines, English headers; documented `Lineitem SKU`/export `Lineitem sku` and `Canceled at`/`Cancelled at` aliases | Missing/duplicate required headers, malformed row widths, localized schemas |
| Orders | `paid`, uncancelled, positive merchandise total, INR | Pending, partially paid, cancelled, refunded, zero-value orders, other currencies |
| Items | Multiple lines, positive integer quantity, nonblank SKU unique within each order | Repeated SKU in one order, missing SKU, removed lines, incomplete totals |
| Money | Decimal strings with at most 2 places, exact paise | Floats, scientific notation, negative/nonfinite values, implicit rounding |
| Adjustments | Shipping charged, tax, order/line discounts and refunded amount must explicitly be zero | Discounts including automatic discounts, taxes, shipping income, duties/tips, refund lifecycle, chargebacks, FX |
| Transactions | Separate CSV, `sale` or `capture`, `success`, INR; full sum exactly equals each order | Refund, authorization, failure, pending, partial capture, orphan transaction, duplicate/indistinguishable rows |
| Costs | Required per-order historical unit costs per SKU, actual fulfilment cost, per-event fees | Guessed zero costs, current catalogue costs substituted for historical costs, automatic provider-fee estimation |
| Identity | Caller-supplied stable customer and provider transaction IDs; store namespace | Inferring identity from emails, assuming a Payment Reference is a successful capture, automatic multi-store consolidation |
| Time | Offset-bearing timestamp converted to explicitly configured IANA store timezone | Naive timestamps, captures dated before order date, events after `--as-of` |
| Refresh | Same snapshot replay, new complete orders in subsequent batches | Changes to previously imported order lines, prices, costs, IDs; deleting records; live change capture |

Scope is merchandise sales. Gift-card issuance, store-credit tender and other liability movements are unsupported and may not be identifiable from these CSV columns alone: exclude them only through a reviewed, documented source selection, or stop and use richer source data. Do not claim that structural checks detect every unsupported business case.

These are deliberate rejection boundaries, not claims that Shopify lacks those features. A whole input fails; unsupported orders are not silently filtered. Shopify's `Source` is an order source, not marketing attribution, so channel comes from explicit metadata. Use `Unattributed` unless you have defensible attribution.

## Export and prepare

1. In Shopify Admin → Orders → Export, select the intended orders and export the native CSV. Export transaction histories for the same orders. Preserve the untouched files locally. Use a known-complete set; the adapter cannot verify your admin filters, pagination, completeness, or freshness.
2. Keep exports outside the repository (or in ignored `store-exports/`). Never put customer exports, context files, databases or quarantine payloads in GitHub or the public demo.
3. Create a metadata template. This refuses to overwrite an existing file:

```sh
python -m merchantops.shopify prepare --orders store-exports/orders.csv --transactions store-exports/transactions.csv --context store-exports/context.json
```

4. Fill **every null** in that local JSON:
   - `store`: stable lowercase slug, e.g. `my-store`; one database per store.
   - `timezone`: actual store IANA timezone, e.g. `Asia/Kolkata`.
   - `orders[Id].customer_id`: stable pseudonymous customer key from a trusted customer mapping. Do not enter email/address. Reusing or splitting a customer key changes retention.
   - `channel`: explicit attribution label or `Unattributed`.
   - `shipping_cost`: actual fulfilment expense, not the Orders CSV `Shipping` charge.
   - `unit_costs[SKU]`: historical unit COGS for that particular order, as decimal rupee strings.
   - `transactions[hash].transaction_id`: verified provider event ID, unique across this store; prefix with provider if needed. `fee`: actual transaction expense as a decimal rupee string. An explicit `"0.00"` is valid only if genuinely zero.

The transaction template includes each source row as `reference` so you can match date, gateway, amount and order against provider records. Its SHA-256 dictionary key is only a lookup key, **not** an inferred provider ID. Do not change the reference. The documented transaction CSV lacks a transaction-ID column; indistinguishable transaction rows are rejected rather than assigned arbitrary row numbers. A changed export needs a freshly prepared context with the same verified underlying IDs/costs.

5. Run and inspect local reports:

```sh
python -m merchantops.shopify run --orders store-exports/orders.csv --transactions store-exports/transactions.csv --context store-exports/context.json --database store.duckdb --as-of 2026-06-30 --report-dir store-reports
```

The command prints source hashes, reconciled counts/amounts, inserted records, and dbt results. `summary.json` and CSV reports are local. Date coverage is enforced through the observation boundary. Advertising is not supplied by these exports: reported contribution is **before advertising unless separate canonical spend events have been loaded**. Missing ad data must not be described as measured zero acquisition cost or used to claim ROAS/CAC performance.

## Mapping and safeguards

- The first order row supplies `Id`, totals and status. Blank-ID continuation rows must be contiguous with that order; their Name must match or be blank, and any repeated order fields must agree. Repeated header rows are rejected. No financial total is summed once per item.
- Merchandise sum must equal both Subtotal and Total after all unsupported components have been required to be zero. Captures must equal that amount for every order. These checks detect many incomplete/edited extracts; they cannot prove upstream truth.
- CSV contains no stable native line ID. For this restricted profile, line key is a SHA-256 of `[order ID, SKU]` within the store namespace. Unique-SKU restriction and exact existing-line-set comparison prevent row reordering, removed lines or extra lines from silently changing an imported order. A product rename does not change SKU-level metrics. Product grouping uses SKU, not display name.
- Native customer names, emails, addresses, notes and payment-reference lists are ignored. Adapter receipts contain hashes and aggregate counts, not those fields. Files stay local. Hashes are provenance, not proof of completeness or authenticity.
- Conversion/reconciliation finishes before opening the destination database. Existing-line-set checks and core atomic ingestion run under the CLI's single-writer lock. Parser errors do not create quarantine; raw ingestion conflicts follow the core's quarantine behavior. Nothing is published by the import command.
- Retrying an unchanged snapshot inserts zero rows. Changed immutable values fail rather than overwrite. A successful import followed by dbt failure leaves raw data committed and the watermark unadvanced; retry the exact input. Reports are only exported after successful dbt checks.
- A partial snapshot may include only new complete orders. Omitting a previously imported order does not delete it. Missing orders outside a supplied file are undetectable. Do not reuse the database for another store or mix direct canonical mutations into Shopify order records.

## Reproducible example

`examples/shopify/` contains two CSVs and fully populated synthetic metadata. One order has two tees at ₹50 and a bag at ₹30, paid with ₹80 + ₹50 captures. COGS is ₹40, fulfilment ₹5, fees ₹2.60: **₹82.40 contribution before advertising**, ₹130 captured, no collection gap. A UTC timestamp on 31 January converts to 1 February in Asia/Kolkata; February is the expected reporting month.

Run the command in README and then run it again: first inserts five records, replay inserts zero. `tests/test_shopify.py` verifies this by executing the actual CLI, then comparing all seven model outputs after a full refresh. The public build reruns this checked-in example and publishes `shopify-example.json` separately from the larger synthetic-store dashboard.

## Next verification needed

Obtain consented/redacted native exports plus source cost and provider records; reconcile every supported order against Shopify and provider totals before relying on reports. Prioritize explicit tax/shipping-income and discount-allocation models next, then stable event-level refund data. This is an offline adapter with a narrow contract, not universal Shopify integration or certified financial reporting.
