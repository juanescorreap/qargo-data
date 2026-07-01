{{ config(
    materialized='incremental',
    incremental_strategy='append',
    on_schema_change='append_new_columns'
) }}

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
        when lower("Revenue Center") like '%beverage%' then 'Beverage'
        when lower("Revenue Center") like '%food%'     then 'Food'
        when lower("Revenue Center") like '%retail%'   then 'Retail'
        when lower("Revenue Center") like '%combo%'    then 'Food'
        else 'Other'
    end as revenue_center,

    "Net Sales"      as net_sales,
    "Order ID"       as order_id,
    "Order ID"       as order_ref,   -- true per-order key (PAR Order ID is a real order id)
    1.0              as qty,          -- PAR exposes no qty (CSV+API are one row per item line); 1 per line is the only available value
    0.0              as tip_amount,
    upper(trim("Destination"))  as destination,
    "Employee Name"  as employee_name,
    "Taxes"          as tax_amount,
    "Discount Total" as discount_total,
    upper(trim("Item Name"))                                         as product_name,
    regexp_replace(upper(trim("Item Name")), '^[0-9]+\s*OZ\s+', '') as product_canonical_name,
    "_source_system"                                                as _source_system  -- 'par2' (CSV) | 'par_api', post-C4 split

from {{ ref('bronze_par2') }}
where
    "Voided"          = false
    and "Is Modifier" = false
    and "Net Sales"   is not null
    {% if is_incremental() %}
    and cast("Date" as date) > (
        select coalesce(max(sale_date), '2000-01-01'::date) from {{ this }}
    )
    {% endif %}
