{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['store_name', 'sale_date'],
    on_schema_change='append_new_columns'
) }}

-- C5 watermark = _ingested_at (load time), NOT sale_date. Late/retro/backfilled
-- rows carry an old sale_date but a fresh _ingested_at, so they are now processed.
-- delete+insert on the PARTITION key (store_name, sale_date) mirrors the bronze
-- reload grain: CSV re-inserts a whole date range, the API re-inserts a whole
-- Location+Date — so any reprocessed (store, date) partition arrives complete and
-- replaces its silver counterpart wholesale. _source_system is intentionally OUT of
-- the key so a CSV load that supersedes prior API rows for the same (store, date)
-- (bronze_par2 CSV-over-API precedence) cleans up the stale API rows too.

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
    upper(trim("Employee Name"))  as employee_name,  -- match dim_employee's upper(trim) contract (ls2 already normalizes Staff); prevents the silent employee_key=0 join-bug for any consumer of stg_orders.employee_name
    "Taxes"          as tax_amount,
    "Discount Total" as discount_total,
    eff_item_name                                          as product_name,
    regexp_replace(eff_item_name, '^[0-9]+\s*OZ\s+', '')  as product_canonical_name,
    "_source_system"                                       as _source_system,  -- 'par2' (CSV) | 'par_api', post-C4 split
    "_ingested_at"                                         as _ingested_at     -- C5 load-time watermark

from src
where
    "Voided"          = false
    and "Is Modifier" = false
    and "Net Sales"   is not null
    {% if is_incremental() %}
    and "_ingested_at" > (
        select coalesce(max(_ingested_at), '2000-01-01'::timestamptz) from {{ this }}
    )
    {% endif %}
