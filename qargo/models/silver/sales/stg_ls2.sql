{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['store_name', 'sale_date'],
    on_schema_change='append_new_columns'
) }}

-- C5 watermark = _ingested_at (load time). delete+insert on the partition key
-- (store_name, sale_date) mirrors the LS2 file reload grain (a file = one store,
-- a date range), so a reprocessed partition replaces its silver counterpart.

select
    cast("Date" as date) as sale_date,

    upper(trim(
        case
            when "Location" ilike 'Qargo Coffee %' then substring("Location" from 14)
            when "Location" ilike 'Qargo %'        then substring("Location" from 7)
            else "Location"
        end
    )) as store_name,

    case
        when split_part("Group", '(', 1) ilike '%beverage%'      then 'Beverage'
        when split_part("Group", '(', 1) ilike '%bottled drink%'  then 'Beverage'
        when split_part("Group", '(', 1) ilike '%food%'           then 'Food'
        when split_part("Group", '(', 1) ilike '%bakery%'         then 'Food'
        when split_part("Group", '(', 1) ilike '%grab%'           then 'Food'
        when split_part("Group", '(', 1) ilike '%taste of italy%' then 'Food'
        when split_part("Group", '(', 1) ilike '%combo%'          then 'Food'
        when split_part("Group", '(', 1) ilike '%cold good%'      then 'Food'
        when split_part("Group", '(', 1) ilike '%retail%'         then 'Retail'
        else 'Other'
    end as revenue_center,

    "FinalPrice"          as net_sales,
    "Account"             as order_id,
    "Reference"           as order_ref,   -- true per-transaction key; Account groups ~5.5 orders (undercount), Reference is per-receipt
    "Qty"                 as qty,          -- real per-line quantity (signed: negatives = returns/refunds)
    0.0                   as tip_amount,
    null::text            as destination,
    upper(trim("Staff"))  as employee_name,
    "TaxAmount"           as tax_amount,
    "Discount"            as discount_total,
    upper(trim("Item"))   as product_name,
    regexp_replace(upper(trim("Item")), '\s*\(\s*[0-9]+\s*OZ\s*\)\s*[A-Z]{0,3}\s*$', '') as product_canonical_name,
    'ls2'                 as _source_system,
    "_ingested_at"        as _ingested_at     -- C5 load-time watermark

from {{ ref('bronze_ls2') }}
where
    split_part("Group", '(', 1) not ilike '%modifier%'
    and "FinalPrice" is not null
    {% if is_incremental() %}
    and "_ingested_at" > (
        select coalesce(max(_ingested_at), '2000-01-01'::timestamptz) from {{ this }}
    )
    {% endif %}
