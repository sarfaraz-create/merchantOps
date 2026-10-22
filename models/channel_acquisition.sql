-- First observed order; deterministic same-day tie break by order_id.
with ranked as (
 select *,row_number() over(partition by customer_id order by ordered_at,order_id) as rn from {{ source('raw','orders') }}
), acquired as (
 select channel,count(*) as first_customers from ranked where rn=1 group by channel
), economics as (
 select channel,sum(ad_spend)::bigint as ad_spend,sum(net_revenue)::bigint as net_revenue
 from {{ ref('monthly') }} group by channel
)
select e.*,coalesce(a.first_customers,0)::bigint as first_customers,
 e.ad_spend*1.0/nullif(a.first_customers,0) as first_order_cac_paise,
 e.net_revenue*1.0/nullif(e.ad_spend,0) as blended_revenue_to_spend
from economics e left join acquired a using(channel)
