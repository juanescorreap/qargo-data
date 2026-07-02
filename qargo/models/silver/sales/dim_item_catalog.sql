{{ config(materialized='table') }}

-- C3 (Option B, interim): ItemId → product lookup built from the CSV source.
-- The PAR GetOrders API returns only ItemId per line (no name/PLU/category), so
-- API rows in raw_par2_api arrive with Item Name / Item PLU = NULL. This catalog
-- lets stg_par2 enrich those rows by joining on Item ID.
--
-- Grain: one row per Item ID. ~112 Item IDs have had >1 name over time; the
-- canonical name/PLU/revenue_center is taken from the MOST RECENT CSV occurrence
-- (max sale_date, name as deterministic tie-break).
--
-- Layer = silver: stg_par2 (silver) consumes this, so it cannot live in gold
-- (that would create a silver → gold → silver cycle). It is a derived/deduped
-- lookup, not raw bronze, so silver is the correct home.
-- Revenue Center here is the DESCRIPTIVE CSV value (e.g. 'Beverages', 'FOOD'),
-- never the numeric DayPartId the API writes — that is exactly why it can repair
-- the API category.

with csv_items as (
    select
        "Item ID"                as item_id,
        upper(trim("Item Name")) as item_name,
        "Item PLU"               as item_plu,
        "Revenue Center"         as revenue_center,
        "Date"                   as sale_date
    from {{ source('bronze', 'raw_par2_csv') }}
    where "Item ID"   is not null
      and "Item Name" is not null
      and trim("Item Name") <> ''
),

ranked as (
    select
        item_id, item_name, item_plu, revenue_center,
        row_number() over (
            partition by item_id
            order by sale_date desc, item_name
        ) as rn
    from csv_items
)

select
    item_id,
    item_name,
    item_plu,
    revenue_center
from ranked
where rn = 1
