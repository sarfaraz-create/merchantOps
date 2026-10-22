# MerchantOps: hiring and merchant-value assessment

23 October 2026. This is a critical assessment and proposed direction, not customer research, observed business impact, or a claim that these workflows are shipped.

## Is it worth putting on a resume?

Yes, as an independently defensible analytics-engineering portfolio project. Not yet as evidence of enterprise adoption, money recovered, production-scale operation, or product-market fit. A recruiter can see relevance; a hiring manager still needs to establish that the candidate understands the work. A polished interface and an AI-generated repository do not establish that understanding.

| Role | Useful evidence now | Missing proof |
|---|---|---|
| Data Analyst | Explicit metric definitions, sales versus payments, refund timing, integer-money calculations, meaningful SQL tests | A real business question investigated with an operator, quality limits quantified, a decision or workflow changed |
| Solutions Engineer | A reproducible importer, explicit adapter contract, failure recovery, honest unsupported inputs | Customer discovery, real source-system mapping and reconciliation, deployment/permissions, operator handoff |
| Product Manager | Scope choices and financial edge-case reasoning | User evidence, prioritization against existing alternatives, usability observations, adoption or task-success measurements |

The current project is strongest as analytics engineering evidence and weaker as standalone PM evidence. Passing tests on synthetic data is useful but not a business outcome. A 100,000-order run measures a specific local workload, not reliability for a brand with millions in monthly sales.

Interview bar: explain the refund story without technical jargon; derive the numbers on paper; identify a wrong join; predict a duplicate import's effect; implement a small change and diagnose a failing test. If Sarfaraz cannot do those independently, the project should not be presented as mastery. The repository openly states AI assistance. No resume is changed by this assessment.

## Would a large brand buy this today?

I would not approve it as a financial system of record or a production purchasing decision on current evidence. It could justify a supervised, read-only evaluation on a carefully scoped extract.

The critical gap is that the most interesting demonstration—refund approval versus returned money—uses the canonical fixture, while the Shopify CSV adapter currently rejects refunds, discounts and tax. Those restrictions are honest but exclude ordinary merchant activity. Supplementing costs and transaction IDs manually may also create more work than it saves. No real export has been validated, and there is no source-to-bank payout matching, operational exception workflow, access control or production operating history.

The competing baseline is not “no analytics.” Shopify already supplies [profit reports](https://help.shopify.com/en/manual/reports-and-analytics/shopify-reports/report-types/default-reports/profit-reports) and a [Shopify Payments activity report](https://help.shopify.com/en/manual/payments/shopify-payments/payouts/payouts-activity-report). The latter has provider-scope limits. Therefore “another margin dashboard” is not a sufficient reason to switch. MerchantOps must prove a specific gap in the merchant's existing workflow, rather than assume it.

## A narrower product hypothesis worth testing

**Help a finance/operations reviewer explain and resolve refund mismatches across the order system and payment provider, with evidence for every amount.**

The useful daily output would say: which approved refunds have no matching successful return, how much is outstanding, how long each has waited, what source records support it, who is reviewing it, and what resolution is recorded. An unmatched record is an exception to investigate, not automatically lost money, a failed refund, or fraud. Settlement timing and provider status can explain legitimate differences.

The current model supplies part of the calculation. Aging, provider links, thresholds, assignment, resolution history and real-source coverage are proposed work, not existing features. Begin with one provider and one store; do not claim cross-platform completeness before reconciliation.

## What a merchant doing millions a month would require

1. **A trustworthy coverage statement.** Last successful load, source totals matched, missing-cost share, rejected records and their amounts, unsupported transaction share. Missing inputs must make the affected metric incomplete, not quietly make margins look better.
2. **A short, actionable review list.** Sort by amount and age, show the exact order and provider events, distinguish ordinary settlement delay from a discrepancy, and provide a next action. Charts alone do not close an exception.
3. **Explanations that survive finance review.** Show sale/approval/payment dates separately, before/after amounts, accounting policies and source links. Explain discount, tax, shipping, fee and inventory effects before making a profit claim.
4. **Low operating burden.** Predictable imports, retry/recovery, no accidental double counts, notifications only for meaningful exceptions, clear ownership and access controls. Manual enrichment cannot expand linearly with every order indefinitely.
5. **Demonstrated value beyond existing tools.** A reviewer completes a real task with fewer errors or less effort, with source-confirmed outcomes. Flagged value is not recovered value; contribution is not cash or net profit.

## Next validation gate, before expanding features

Find one willing merchant finance/operations reviewer. Observe their current refund-review workflow and alternatives; do not message anyone or access a store without authorization. Obtain consented/redacted order, refund and payment extracts plus expected reconciliations for one historical period. Extend the source contract to represent those ordinary events before using them in the demonstration.

Use the existing workflow as a baseline. Record import preparation time, matched/unmatched amounts, coverage, false alerts, reviewer task completion time, and whether each discrepancy was explained or corrected. Agree acceptance criteria with the reviewer before the pilot. Verify any claimed recovery against source records. Do not invent targets or declare uplift from synthetic scenarios.

If the existing Shopify/provider report solves the task as well with less effort, narrow the problem further or stop. That finding is more credible product judgment than adding an LLM, MCP tools or more charts to a workflow nobody needs.
