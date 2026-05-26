with stores as (
    select distinct store_name
    from {{ ref('stg_orders') }}
)

select
    abs(hashtext(store_name)::bigint)         as store_key,
    store_name,
    case
        when store_name like 'MEIJER%'       then 0.04
        when store_name = 'LAS VEGAS'        then 0.08
        else                                      0.07
    end::numeric(5, 2)                       as royalty_rate,
    true                                     as is_active
from stores
