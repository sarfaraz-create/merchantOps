# Data dictionary — normalized v3

The full named-field source contract and validation rules are in integration.md. Synthetic generator: seed 42, 1 January–30 June 2026, INR paise, one calendar-day timezone. Source counts and hash are in source-manifest.json. The pattern of more discounts, spend and refund probability later in the period is intentionally generated, not evidence about real commerce.

| Model | Grain | Definition |
|---|---|---|
| line_economics | line_id | quantity × unit price − line discount − granted line refunds; COGS = quantity × historical unit cost |
| order_economics | order_id | aggregate line economics; subtract shipping once and successful payment fees once |
| monthly | month × channel | charges/COGS/shipping on sale date, refund grants on grant date, successful fees on payment date, advertising on spend date |
| payment_reconciliation | order_id | captured − returned cash; collection gap = charged − captured; refund payable = granted − returned |
| sku_returns | channel × product | distinct orders containing SKU, units, distinct refunded orders, refund value / charged value, merchandise contribution |
| channel_acquisition | channel over snapshot | first-observed customers; CAC = spend / those customers; blended revenue/spend includes repeat purchases |
| retention | first-observed-purchase month | later-date purchase through day 30, only fully observed 30-day windows |

All monetary totals are integer paise. Ratios can be floats; zero denominators are NULL, displayed as —. Same-day first-purchase ties use order_id. A customer appearing before source coverage may be misclassified as new; never label this proven lifetime acquisition. Fully refunded orders still count for purchase retention.

SKU merchandise contribution excludes shipping, payment fees and advertising, which are shared order/channel costs. SKU order counts are not additive across SKUs: an order containing two products appears in both groups. Partial refunds count once per order/SKU. No returned quantity or restocking assumption is inferred from refunded money.

Revenue and cash are different. Failed payments do not reduce or add revenue. A granted refund reduces merchandise revenue even if cash is still owed. Uncollected sales and unpaid refund liabilities remain visible. This is not audited financial reporting or statutory accounting.
