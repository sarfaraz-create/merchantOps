select * from {{ ref('payment_reconciliation') }} where
 cash_net != charged-refund_granted-collection_gap+refund_payable
 or collection_gap<0 or refund_payable<0
