-- C5 detection: bronze→silver coverage for LS2.
-- Every sale_date with QUALIFYING rows in bronze_ls2 must exist in stg_ls2.
-- Non-empty result = bronze→silver coverage gap (silent late/backfill drop).
-- The bronze side mirrors stg_ls2's filters (modifier group / FinalPrice) so
-- legitimately-filtered dates are not reported. dbt test passes on zero rows.

with bronze as (
    select distinct
        'ls2'                as source_system,
        cast("Date" as date) as sale_date
    from {{ ref('bronze_ls2') }}
    where split_part("Group", '(', 1) not ilike '%modifier%'
      and "FinalPrice" is not null
),

silver as (
    select distinct _source_system as source_system, sale_date
    from {{ ref('stg_ls2') }}
)

select
    b.source_system,
    b.sale_date
from bronze b
left join silver s
    on s.source_system = b.source_system
   and s.sale_date     = b.sale_date
where s.sale_date is null
