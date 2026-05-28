{{ config(materialized='table') }}

with raw as (
    select distinct upper(trim("Destination")) as destination_name
    from {{ source('bronze', 'raw_par2') }}
    where "Destination" is not null
      and trim("Destination") <> ''
)
select
    abs(hashtext(destination_name)::bigint) as destination_key,
    destination_name,
    case
        when destination_name ilike '%dine%'     then 'In-Store'
        when destination_name ilike '%drive%'    then 'Drive-Thru'
        when destination_name ilike '%go%'       then 'Takeout'
        when destination_name ilike '%delivery%' then 'Delivery'
        when destination_name ilike '%cater%'    then 'Catering'
        else                                          'Other'
    end as channel
from raw

union all

select 0::bigint, 'UNKNOWN', 'Unknown'
