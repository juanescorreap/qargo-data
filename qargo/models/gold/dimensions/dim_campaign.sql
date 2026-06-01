{{ config(materialized='table') }}

with seed_data as (
    select
        upper(trim(product_canonical_name)) as product_canonical_name,
        upper(trim(campaign_name))          as campaign_name,
        campaign_start_date::date           as campaign_start_date,
        campaign_end_date::date             as campaign_end_date
    from {{ ref('product_campaign_map') }}
    where campaign_name                 is not null
      and trim(campaign_name)           <> ''
      and product_canonical_name        is not null
      and trim(product_canonical_name)  <> ''
)

select
    abs(hashtext(campaign_name)::bigint) as campaign_key,
    campaign_name,
    product_canonical_name,
    campaign_start_date,
    campaign_end_date
from seed_data

union all

select 0::bigint, 'NO CAMPAIGN', null, null, null
