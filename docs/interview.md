# Demonstrate understanding, not just a dashboard

## 90-second walkthrough
“This answers two operator questions: why contribution changed, and whether money was actually collected or refunded. The demo data is synthetic. The local importer and tests are real.”

1. Show the financial bridge and distinguish contribution from profit.
2. Inspect a SKU. Explain why order shipping/fees/ads are not silently allocated to it.
3. Show refund payable. A credit can reduce revenue before the provider returns cash.
4. Step through the recorded two-item/split-payment fixture: contribution ₹72.60 → ₹52.60 on refund grant → unchanged on duplicate → ₹42.60 after ₹10 extra ads and a cash return. Cash return clears the payable, not revenue again.
5. Open tests/test_incremental.py. Explain why ingestion sequence catches an old event and why a failed dbt run cannot advance the watermark.

## Do these exercises before claiming independent proficiency
- Draw the grain of each source. Predict the wrong total from joining two items and two payments directly, then show the correct aggregation.
- Change the partial refund from ₹20 to ₹25. Predict line revenue, order contribution, monthly reporting and cash liability before running anything.
- Delay the cash refund to another month. Explain which reports change and which do not.
- Add a historical first purchase. Explain why acquisition and retention are rebuilt.
- Deliberately fail a dbt test after source ingestion. Confirm watermark behavior and recover through replay. Explain why readers should not use partial marts.
- Map a real platform export schema on paper. Identify every unsupported field/event rather than guessing costs or forcing chargebacks into refunds.

## Limits to state plainly
AI-assisted implementation. No real merchant/platform connector or realised business results. The benchmark includes more builds in the incremental scenario, so its total runtime is not a speed comparison. Local single-writer operation; no multi-user hosting or tax/FX/correction support.
