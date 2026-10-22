{{ config(materialized='incremental',unique_key='order_id',incremental_strategy='delete+insert') }}
with cash as (select order_id,
 sum(case when kind='capture' and status='succeeded' then amount else 0 end)::bigint as captured,
 sum(case when kind='refund' and status='succeeded' then amount else 0 end)::bigint as returned,
 count(*) filter(where status='failed')::bigint as failed_attempts
 from {{ source('raw','payments') }} group by order_id)
select o.order_id,o.channel,(o.gross-o.discount)::bigint as charged,o.refunded as refund_granted,
 coalesce(captured,0)::bigint as captured,coalesce(returned,0)::bigint as returned,
 (o.gross-o.discount-coalesce(captured,0))::bigint as collection_gap,
 (o.refunded-coalesce(returned,0))::bigint as refund_payable,
 (coalesce(captured,0)-coalesce(returned,0))::bigint as cash_net,
 coalesce(failed_attempts,0)::bigint as failed_attempts
from {{ ref('order_economics') }} o left join cash using(order_id)
{% if is_incremental() %}where o.order_id in ({{ changed_orders() }}){% endif %}
