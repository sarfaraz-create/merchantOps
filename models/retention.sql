-- 30-day repurchase, exclusive first date and inclusive day 30; immature users excluded.
with first_order as (
 select customer_id,min(ordered_at) as acquired from {{ source('raw','orders') }} group by customer_id
), customers as (
 select f.customer_id,f.acquired,
 max(case when o.ordered_at>acquired and o.ordered_at<=acquired+30 then 1 else 0 end) as repeated
 from first_order f join {{ source('raw','orders') }} o using(customer_id)
 where acquired<=date '{{ var("as_of", "2026-06-30") }}'-30
 and o.ordered_at<=date '{{ var("as_of", "2026-06-30") }}'
 group by all
)
select date_trunc('month',acquired)::date as cohort,count(*) as eligible_customers,
 sum(repeated)::bigint as repeat_customers, sum(repeated)*1.0/count(*) as retention_30d
from customers group by all
