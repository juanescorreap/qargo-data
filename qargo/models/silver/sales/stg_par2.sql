{{ config(
    materialized='incremental',
    incremental_strategy='append',
    on_schema_change='append_new_columns'
) }}

with src as (
    select
        b.*,
        -- C3: effective revenue center. CSV rows carry a DESCRIPTIVE value
        -- ('Beverages','FOOD','RETAIL',...). API rows carry a numeric DayPartId
        -- (e.g. '640207795') because GetOrders exposes no RevenueCenterId — detect
        -- the purely-numeric case and substitute the catalog's descriptive value so
        -- the category derives correctly. CSV Revenue Center is never numeric
        -- (verified 0 rows), so CSV rows always keep their own value.
        case
            when b."Revenue Center" ~ '^[0-9]+$' then cat.revenue_center
            else b."Revenue Center"
        end as eff_revenue_center,
        -- C3: API rows have Item Name = NULL; fall back to the catalog name.
        -- CSV rows keep their own name (non-null), so the coalesce is a no-op there.
        coalesce(upper(trim(b."Item Name")), cat.item_name) as eff_item_name
    from {{ ref('bronze_par2') }} b
    left join {{ ref('dim_item_catalog') }} cat
        on b."Item ID" = cat.item_id
)

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
        when lower(eff_revenue_center) like '%beverage%' then 'Beverage'
        when lower(eff_revenue_center) like '%food%'     then 'Food'
        when lower(eff_revenue_center) like '%retail%'   then 'Retail'
        when lower(eff_revenue_center) like '%combo%'    then 'Food'
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
    eff_item_name                                          as product_name,
    regexp_replace(eff_item_name, '^[0-9]+\s*OZ\s+', '')  as product_canonical_name,
    "_source_system"                                       as _source_system  -- 'par2' (CSV) | 'par_api', post-C4 split

from src
where
    "Voided"          = false
    and "Is Modifier" = false
    and "Net Sales"   is not null
    {% if is_incremental() %}
    and cast("Date" as date) > (
        select coalesce(max(sale_date), '2000-01-01'::date) from {{ this }}
    )
    {% endif %}
