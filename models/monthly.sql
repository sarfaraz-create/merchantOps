{{ config(materialized='incremental',unique_key=['month','channel'],incremental_strategy='delete+insert') }}
-- Revenue follows order date; refund grants and actual payment fees follow their event dates.
with ledger as (
 select date_trunc('month',ordered_at)::date as month,channel,gross,discount,0::bigint as refunds,cogs,shipping,0::bigint as fees,0::bigint as ad_spend,1 as orders from {{ ref('order_economics') }}
 union all select date_trunc('month',r.refunded_at)::date,o.channel,0,0,r.amount,0,0,0,0,0
 from {{ source('raw','refunds') }} r join {{ source('raw','line_items') }} l using(line_id) join {{ source('raw','orders') }} o using(order_id)
 union all select date_trunc('month',p.occurred_at)::date,o.channel,0,0,0,0,0,p.fee,0,0 from {{ source('raw','payments') }} p join {{ source('raw','orders') }} o using(order_id) where p.status='succeeded'
 union all select date_trunc('month',spent_at)::date,channel,0,0,0,0,0,0,amount,0 from {{ source('raw','spend') }}
), affected as (
 select date_trunc('month',ordered_at)::date as month,channel from {{ source('raw','orders') }} where order_id in ({{ changed_orders() }})
 union select date_trunc('month',r.refunded_at)::date,o.channel from {{ source('raw','refunds') }} r join {{ source('raw','line_items') }} l using(line_id) join {{ source('raw','orders') }} o using(order_id) where r._batch_id>{{ var('lower_batch',0) }}
 union select date_trunc('month',p.occurred_at)::date,o.channel from {{ source('raw','payments') }} p join {{ source('raw','orders') }} o using(order_id) where p._batch_id>{{ var('lower_batch',0) }}
 union select date_trunc('month',spent_at)::date,channel from {{ source('raw','spend') }} where _batch_id>{{ var('lower_batch',0) }}
)
select month,channel,sum(orders)::bigint as orders,sum(gross)::bigint as gross,sum(discount)::bigint as discount,
 sum(refunds)::bigint as refunds,sum(cogs)::bigint as cogs,sum(shipping)::bigint as shipping,sum(fees)::bigint as fees,
 sum(ad_spend)::bigint as ad_spend,sum(gross-discount-refunds)::bigint as net_revenue,
 sum(gross-discount-refunds-cogs-shipping-fees-ad_spend)::bigint as contribution
from ledger
{% if is_incremental() %}where (month,channel) in (select month,channel from affected){% endif %}
group by all
