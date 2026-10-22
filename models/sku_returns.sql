{{ config(materialized='incremental',unique_key=['channel','product'],incremental_strategy='delete+insert') }}
select channel,product,count(distinct order_id)::bigint as orders,sum(quantity)::bigint as units,
 count(distinct order_id) filter(where refunded>0)::bigint as refunded_orders,
 sum(refunded)::bigint as refund_amount,sum(gross-discount)::bigint as charged_revenue,
 sum(net_revenue)::bigint as net_revenue,sum(merchandise_contribution)::bigint as merchandise_contribution,
 count(distinct order_id) filter(where refunded>0)*1.0/count(distinct order_id) as refunded_order_rate,
 sum(refunded)*1.0/nullif(sum(gross-discount),0) as refund_value_rate
from {{ ref('line_economics') }}
{% if is_incremental() %}where (channel,product) in (select channel,product from {{ ref('line_economics') }} where order_id in ({{ changed_orders() }})){% endif %}
group by all
