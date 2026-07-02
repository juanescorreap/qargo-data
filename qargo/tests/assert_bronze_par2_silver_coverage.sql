-- C5 detection: bronze→silver coverage for PAR.
-- Every (source_system, sale_date) that has QUALIFYING rows in bronze_par2 must
-- exist in stg_par2. A non-empty result = a "bronze→silver coverage gap": bronze
-- holds a date silver dropped — the silent failure mode of scenarios a/c/d (late
-- CSV, manual backfill, POS outage). The returned rows name the missing
-- (source, date) pairs. dbt test passes only when zero rows are returned.
--
-- The bronze side mirrors stg_par2's row filters (Voided / Is Modifier / Net Sales)
-- so a date that is legitimately all-voided is NOT reported as a gap.

with bronze as (
    select distinct
        "_source_system"     as source_system,
        cast("Date" as date) as sale_date
    from {{ ref('bronze_par2') }}
    where "Voided"      = false
      and "Is Modifier" = false
      and "Net Sales"   is not null
),

silver as (
    select distinct _source_system as source_system, sale_date
    from {{ ref('stg_par2') }}
)

select
    b.source_system,
    b.sale_date
from bronze b
left join silver s
    on s.source_system = b.source_system
   and s.sale_date     = b.sale_date
where s.sale_date is null
