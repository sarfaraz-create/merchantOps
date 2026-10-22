"""Hand-calculated expectations and plain-language interpretation of the recorded example."""

STORIES = [
    {
        "title": "1 January · The customer pays ₹120",
        "happened": "One customer buys two tees at ₹50 each and one cap at ₹30. A ₹10 discount brings the bill to ₹120. They pay ₹70 and ₹50 in two separate payments.",
        "testing": "Do several products and two payments still count as ONE ₹120 sale?",
        "calculation": "₹130 items − ₹10 discount = ₹120 sales. ₹120 − ₹40 item cost − ₹5 delivery cost − ₹2.40 payment fees = ₹72.60 contribution.",
        "reason": "Add the products once and add the payments separately. Matching every product row to every payment row must not multiply the sale or its costs.",
        "action": "Both payments add up to the bill. No collection or refund follow-up is needed in this example.",
        "expected": [12000, 7260, 12000, 0, 0, 0],
    },
    {
        "title": "4 February · You approve a ₹20 refund",
        "happened": "The customer receives a ₹20 partial refund approval against the tees bought in January. No money has been returned yet.",
        "testing": "Does the refund reduce the amount earned once, while showing that ₹20 still needs to be returned?",
        "calculation": "₹120 sales − ₹20 approved refund = ₹100 net sales. ₹72.60 previous contribution − ₹20 = ₹52.60. ₹20 approved − ₹0 returned = ₹20 still to return.",
        "reason": "This project reduces sales when a refund is approved. February records the ₹20 reduction; January stays at ₹72.60 contribution. Across both months the total is ₹52.60. The original item, delivery and payment costs remain expenses.",
        "action": "Check whether the provider has processed the approved refund. An outstanding amount is a follow-up item, not proof of a failed payment.",
        "expected": [10000, 5260, 12000, 0, 2000, 0],
    },
    {
        "title": "Import again · The same ₹20 refund appears twice",
        "happened": "The exact same refund record is imported again, with the same refund ID and values. This is not another refund to the customer.",
        "testing": "Can an export be imported twice without counting the refund twice?",
        "calculation": "No new refund record is accepted. Net sales stay ₹100; contribution stays ₹52.60; the amount still to return stays ₹20.",
        "reason": "The existing refund ID identifies an event already counted. A second genuine refund would need a different ID. Changing the values under an existing ID would be rejected.",
        "action": "No merchant correction is needed for this exact duplicate. The importer reports zero new records.",
        "expected": [10000, 5260, 12000, 0, 2000, 0],
    },
    {
        "title": "5 February · The provider returns ₹20",
        "happened": "A successful payment-provider record confirms that ₹20 was returned to the customer. There is no extra refund fee in this synthetic example.",
        "testing": "Does returning the money clear the outstanding refund WITHOUT reducing sales a second time?",
        "calculation": "₹20 approved − ₹20 returned = ₹0 still to return. ₹120 received − ₹20 returned = ₹100 net customer payments. Contribution stays ₹52.60.",
        "reason": "The reduction in sales was already recorded at approval. This event records the money moving. Deducting another ₹20 from contribution would count one refund twice. Net customer payments are not your bank balance: fees, payouts and other expenses are separate.",
        "action": "The approved refund now matches a successful return record. This example no longer needs refund-payment follow-up; it does not verify a bank settlement.",
        "expected": [10000, 5260, 12000, 2000, 0, 0],
    },
    {
        "title": "5 February · A separate ₹10 advertising cost arrives",
        "happened": "You import ₹10 of advertising cost for this example’s channel. This is a separate business expense, not part of the customer refund.",
        "testing": "Does an extra cost reduce contribution without changing sales or the customer’s payment balance?",
        "calculation": "₹52.60 previous contribution − ₹10 advertising = ₹42.60. Net sales remain ₹100; payments received remain ₹120; returned money remains ₹20.",
        "reason": "Contribution subtracts the included operating costs from net sales. The cost is recorded at channel level; the tool does not claim that this ad caused the sale or allocate it to a product.",
        "action": "Include the expense when reviewing channel performance. This example alone cannot tell you whether to cut the campaign.",
        "expected": [10000, 4260, 12000, 2000, 0, 1000],
    },
    {
        "title": "6 February · A ₹1 refund refers to an unknown item",
        "happened": "An incoming refund record points to an item that is not in the imported orders. The example deliberately supplies this invalid record.",
        "testing": "Will an unmatched refund be stopped instead of silently changing the report?",
        "calculation": "The whole incoming batch is rejected. ₹0 is added to refunds. Net sales stay ₹100 and contribution stays ₹42.60. One rejected batch is saved for review.",
        "reason": "Without an original item, the tool cannot validate the refund. The rejected input is kept separately for investigation (called quarantine in the technical details). It has no effect on the accepted financial totals.",
        "action": "Find the missing order/item or fix the source mapping, then resubmit. A rejection does not prove fraud and does not establish that the refund is invalid in the real store.",
        "expected": [10000, 4260, 12000, 2000, 0, 1000],
    },
]


def explain(stage, index):
    story = dict(STORIES[index])
    cash = stage["reconciliation"]
    actual = [
        sum(r["net_revenue"] for r in stage["monthly"]),
        sum(r["contribution"] for r in stage["monthly"]),
        cash["captured"],
        cash["returned"],
        cash["refund_payable"],
        sum(r["ad_spend"] for r in stage["monthly"]),
    ]
    expected_counts = [
        (1, 2, 2, 0, 0),
        (1, 2, 2, 1, 0),
        (1, 2, 2, 1, 0),
        (1, 2, 3, 1, 0),
        (1, 2, 3, 1, 0),
        (1, 2, 3, 1, 1),
    ]
    counts = tuple(
        stage[k]
        for k in ["orders", "line_items", "payments", "refunds", "quarantined_batches"]
    )
    expected_inserts = [5, 1, 0, 1, 1, None]
    valid_ingestion = (
        stage["ingestion"].get("inserted_rows") == expected_inserts[index]
        if index < 5
        else "Orphan refund" in stage["ingestion"].get("rejected", "")
    )
    story["actual"] = actual
    story["passed"] = (
        actual == story["expected"]
        and counts == expected_counts[index]
        and valid_ingestion
    )
    if not story["passed"]:
        raise ValueError(
            f"Refund walkthrough step {index+1} failed its independent expected result"
        )
    return story
