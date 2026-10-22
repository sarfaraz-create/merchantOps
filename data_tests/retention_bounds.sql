select * from {{ ref('retention') }} where repeat_customers>eligible_customers or retention_30d<0 or retention_30d>1
