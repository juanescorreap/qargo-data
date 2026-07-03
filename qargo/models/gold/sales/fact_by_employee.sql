{{ config(
    materialized='incremental',
    unique_key=['date_key', 'store_key', 'employee_key'],
    on_schema_change='append_new_columns'
) }}

-- Grain: (date_key, store_key, employee_key) = one row per employee per store per day.
-- Rebuilds the dropped fact_sales_by_employee (recovered from git 378457f^) to restore
-- the per-employee metrics: Up-selling Leaderboard, Discount Audit, Labor Efficiency,
-- Top Employees.
--
-- Source limitations (documented, not bugs):
--   tip_amount  -> ALWAYS 0. Both staging models hardcode 0.0 (no tip in the POS feeds).
--                  => Tip Performance Index is NOT rebuildable; kept for forward-compat.
--   employee_key = 0 (UNKNOWN) absorbs rows whose name does not map to dim_employee:
--                  PAR API numeric IDs (dim_employee excludes numeric-only names) and any
--                  null/blank staff. Named-employee analysis is valid for PAR CSV + LS2.
--                  Filter employee_key <> 0 for leaderboards.
--   Join key is upper(trim(employee_name)): dim_employee stores names ALREADY
--                  upper(trim())-normalized, but stg_par2 emits employee_name in raw case.
--                  Matching on the normalized form lifts named coverage from 4 -> 246
--                  distinct employees (a raw-case join silently dropped 242 PAR CSV names
--                  to UNKNOWN). This mirrors dim_employee's own normalization contract.
--   No shift/hour grain exists (no time-of-sale column), so Shift Productivity per HOUR is
--                  not rebuildable — orders/employee/DAY is the finest approximation.

with orders as (
    select
        sale_date,
        store_name,
        employee_name,
        net_sales,
        order_ref,
        tip_amount,
        tax_amount,
        discount_total,
        _ingested_at
    from {{ ref('stg_orders') }}
    where order_ref is not null and btrim(order_ref) <> ''
    {% if is_incremental() %}
    and _ingested_at > (  -- C5: load-time watermark
        select coalesce(max(_ingested_at), '2000-01-01'::timestamptz) from {{ this }}
    )
    {% endif %}
),

joined as (
    select
        d.date_key,
        s.store_key,
        coalesce(emp.employee_key, 0) as employee_key,
        o.net_sales,
        o.order_ref,
        o.tip_amount,
        o.tax_amount,
        o.discount_total,
        o._ingested_at
    from orders o
    inner join {{ ref('dim_date') }}     d   on o.sale_date                          = d.date
    inner join {{ ref('dim_store') }}    s   on o.store_name                         = s.store_name
    left  join {{ ref('dim_employee') }} emp on upper(trim(coalesce(o.employee_name, 'UNKNOWN'))) = emp.employee_name
)

select
    date_key,
    store_key,
    employee_key,
    sum(net_sales)                                                              as net_sales,
    count(distinct order_ref)                                                   as order_count,
    sum(tip_amount)                                                             as tip_amount,
    sum(tax_amount)                                                             as tax_amount,
    sum(discount_total)                                                         as discount_total,
    round((sum(net_sales) / nullif(count(distinct order_ref), 0))::numeric, 2)  as avg_ticket,
    max(_ingested_at)                                                           as _ingested_at
from joined
group by date_key, store_key, employee_key
