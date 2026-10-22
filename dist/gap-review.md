# MerchantOps release scope — v3

The original playbook calls for independent source grains, incremental handling of late events, three decision views, reproducible failures, measured scale and evidence-linked explanation. Only MerchantOps is in scope; no resume changes.

| Area | Current evidence | Remaining boundary |
|---|---|---|
| Source modelling | Separate orders, quantity-bearing line items, terminal payment events, line refund grants and channel spend | No tax/shipping income/chargebacks/restocking or source updates/deletes |
| Financial correctness | Independent child aggregation, integer paise, revenue/cash separation, collection and refund liabilities | Accounting policies need merchant validation |
| Incremental dbt | Five keyed/partitioned incremental models; actual dbt full-refresh equivalence tests | Two small customer summaries rebuild intentionally; no speedup claim |
| Late data and recovery | Historical refund/spend tests, replay, quarantine, watermark unchanged on failure | Whole dbt DAG is not atomic; readers must await successful run |
| Store integration | Executable named-field JSON importer, examples, mapping/operating contract | No Shopify/WooCommerce/provider API adapter or real store connected |
| Decision views | Channel contribution, SKU returns, repeat purchase, payment reconciliation | Synthetic scenarios only, no causal uplift |
| Scale evidence | 100,000 orders with separately counted items/payments; actual dbt runs and output hashes | Replicated synthetic workload, not production capacity |
| Portfolio clarity | Explicit first-screen purpose, source link, design trade-offs, hand-calculated walkthrough | Independent proficiency and real-user feedback require observation |
| MCP | Deferred | Read-only metric interface follows integration contracts; no arbitrary SQL endpoint |

A universal integration claim is deliberately not made. The next meaningful step is one concrete store adapter, tested against that platform's lifecycle and reconciliation rules.
