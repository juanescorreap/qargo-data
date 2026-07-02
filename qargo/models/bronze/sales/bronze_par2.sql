-- C4: bronze_par2 is the single PAR combining point. It UNIONs the two
-- per-source physical tables (split from the old shared bronze.raw_par2) with
-- explicit CSV-over-API precedence: for any (store, date) present in the CSV
-- source, CSV is authoritative and the API rows are dropped; API only fills
-- (store, date) combinations the CSV never delivered. Result: every
-- (store, date) resolves to exactly one source — no duplicates, no clobbering.

with csv_rows as (
    -- raw_par2_csv has no entry_id (CSV never provided one, and the loader recreates
    -- the table from the DataFrame without it). Add it explicitly as NULL::text so this
    -- branch is column-compatible with raw_par2_api, which carries entry_id (added in C4).
    select *, null::text as entry_id from {{ source('bronze', 'raw_par2_csv') }}
),

api_rows as (
    select * from {{ source('bronze', 'raw_par2_api') }}
),

csv_keys as (
    select distinct "Location" as loc, "Date" as dt
    from csv_rows
)

select * from csv_rows

union all

select a.*
from api_rows a
left join csv_keys k
    on k.loc = a."Location"
   and k.dt  = a."Date"
where k.loc is null   -- API only where CSV has no data for that store/date
