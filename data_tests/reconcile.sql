select 1 as failed where
 (select coalesce(sum(net_revenue),0) from {{ ref('monthly') }}) != (select coalesce(sum(net_revenue),0) from {{ ref('order_economics') }})
 or (select coalesce(sum(contribution),0) from {{ ref('monthly') }}) !=
 (select coalesce(sum(contribution_before_ads),0) from {{ ref('order_economics') }})-(select coalesce(sum(amount),0) from {{ source('raw','spend') }})
