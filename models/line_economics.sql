{{ config(materialized='incremental',unique_key='line_id',incremental_strategy='delete+insert') }}
with refunds as (select line_id,sum(amount)::bigint as refunded from {{ source('raw','refunds') }} group by line_id)
select l.line_id,l.order_id,o.customer_id,o.ordered_at,o.channel,l.product,l.quantity,
 (l.quantity*l.unit_price)::bigint as gross,l.discount,(l.quantity*l.unit_cost)::bigint as cogs,
 coalesce(r.refunded,0)::bigint as refunded,
 (l.quantity*l.unit_price-l.discount-coalesce(r.refunded,0))::bigint as net_revenue,
 (l.quantity*(l.unit_price-l.unit_cost)-l.discount-coalesce(r.refunded,0))::bigint as merchandise_contribution
from {{ source('raw','line_items') }} l join {{ source('raw','orders') }} o using(order_id)
left join refunds r using(line_id)
{% if is_incremental() %}where l.order_id in ({{ changed_orders() }}){% endif %}
