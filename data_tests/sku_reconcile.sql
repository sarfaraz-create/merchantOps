select 1 as failed where
 (select coalesce(sum(net_revenue),0) from {{ ref('sku_returns') }}) != (select coalesce(sum(net_revenue),0) from {{ ref('order_economics') }})
 or (select coalesce(sum(refund_amount),0) from {{ ref('sku_returns') }}) != (select coalesce(sum(amount),0) from {{ source('raw','refunds') }})
 or (select coalesce(sum(first_customers),0) from {{ ref('channel_acquisition') }}) != (select count(distinct customer_id) from {{ source('raw','orders') }})
