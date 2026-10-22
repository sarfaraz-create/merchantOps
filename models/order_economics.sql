{{ config(materialized='incremental',unique_key='order_id',incremental_strategy='delete+insert') }}
-- Aggregate each child independently; joining line items to payments directly multiplies money.
with lines as (select order_id,sum(gross)::bigint as gross,sum(discount)::bigint as discount,
 sum(cogs)::bigint as cogs,sum(refunded)::bigint as refunded,sum(net_revenue)::bigint as net_revenue
 from {{ ref('line_economics') }} group by order_id),
 fees as (select order_id,sum(fee)::bigint as fees from {{ source('raw','payments') }} where status='succeeded' group by order_id)
select o.order_id,o.customer_id,o.ordered_at,o.channel,l.gross,l.discount,l.cogs,o.shipping,
 coalesce(f.fees,0)::bigint as fees,l.refunded,l.net_revenue,
 (l.net_revenue-l.cogs-o.shipping-coalesce(f.fees,0))::bigint as contribution_before_ads
from {{ source('raw','orders') }} o join lines l using(order_id) left join fees f using(order_id)
{% if is_incremental() %}where o.order_id in ({{ changed_orders() }}){% endif %}
