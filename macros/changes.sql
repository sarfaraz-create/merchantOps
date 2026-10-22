{% macro changed_orders() %}
select order_id from {{ source('raw','orders') }} where _batch_id > {{ var('lower_batch',0) }}
union select order_id from {{ source('raw','line_items') }} where _batch_id > {{ var('lower_batch',0) }}
union select l.order_id from {{ source('raw','refunds') }} r join {{ source('raw','line_items') }} l using(line_id) where r._batch_id > {{ var('lower_batch',0) }}
union select order_id from {{ source('raw','payments') }} where _batch_id > {{ var('lower_batch',0) }}
{% endmacro %}
