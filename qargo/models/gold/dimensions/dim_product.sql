{{ config(materialized='table') }}

with par_products as (
    select distinct
        upper(trim("Item Name"))                                         as product_name,
        regexp_replace(upper(trim("Item Name")), '^[0-9]+\s*OZ\s+', '') as product_canonical_name,
        case
            when lower("Revenue Center") like '%beverage%' then 'Beverage'
            when lower("Revenue Center") like '%food%'     then 'Food'
            when lower("Revenue Center") like '%retail%'   then 'Retail'
            when lower("Revenue Center") like '%combo%'    then 'Food'
            else 'Other'
        end                                                              as revenue_center_name
    from {{ ref('bronze_par2') }}   -- C4: unified CSV+API source (was source raw_par2)
    where "Item Name"   is not null
      and trim("Item Name") <> ''
      and "Voided"      = false
      and "Is Modifier" = false
),

ls2_products as (
    select distinct
        upper(trim("Item"))                                              as product_name,
        regexp_replace(upper(trim("Item")), '\s*\(\s*[0-9]+\s*OZ\s*\)\s*[A-Z]{0,3}\s*$', '') as product_canonical_name,
        case
            when split_part("Group", '(', 1) ilike '%beverage%'       then 'Beverage'
            when split_part("Group", '(', 1) ilike '%bottled drink%'   then 'Beverage'
            when split_part("Group", '(', 1) ilike '%food%'            then 'Food'
            when split_part("Group", '(', 1) ilike '%bakery%'          then 'Food'
            when split_part("Group", '(', 1) ilike '%grab%'            then 'Food'
            when split_part("Group", '(', 1) ilike '%taste of italy%'  then 'Food'
            when split_part("Group", '(', 1) ilike '%combo%'           then 'Food'
            when split_part("Group", '(', 1) ilike '%cold good%'       then 'Food'
            when split_part("Group", '(', 1) ilike '%retail%'          then 'Retail'
            else 'Other'
        end                                                              as revenue_center_name
    from {{ source('bronze', 'raw_ls2') }}
    where "Item"        is not null
      and trim("Item")  <> ''
      and split_part("Group", '(', 1) not ilike '%modifier%'
      and "Type"        in ('SALE', 'UPDATE')
),

combined as (
    -- PAR (priority 1) wins over LS2 (priority 2) when same product_name has conflicting
    -- revenue_center_name across systems (e.g. "1 SCOOP" = Food in PAR, Beverage in LS2).
    select product_name, product_canonical_name, revenue_center_name, 1 as src_priority
    from par_products
    union all
    select product_name, product_canonical_name, revenue_center_name, 2 as src_priority
    from ls2_products
),

with_key as (
    select distinct on (product_name)
        abs(hashtext(product_name)::bigint) as product_key,
        product_name,
        product_canonical_name,
        revenue_center_name
    from combined
    where product_name is not null
      and trim(product_name) <> ''
    order by product_name, src_priority
)

select * from with_key

union all

select 0::bigint, 'UNKNOWN', 'UNKNOWN', 'Other'
