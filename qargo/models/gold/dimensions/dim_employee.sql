{{ config(materialized='table') }}

with par_staff as (
    select distinct upper(trim("Employee Name")) as employee_name
    from {{ ref('bronze_par2') }}   -- C4: unified CSV+API source (was source raw_par2)
    where "Employee Name" is not null
      and trim("Employee Name") <> ''
      and "Employee Name" !~ '^[0-9]+$'  -- exclude numeric IDs written by the API
),
ls2_staff as (
    select distinct upper(trim("Staff")) as employee_name
    from {{ source('bronze', 'raw_ls2') }}
    where "Staff" is not null
      and trim("Staff") <> ''
),
combined as (
    select employee_name from par_staff
    union
    select employee_name from ls2_staff
)
select
    abs(hashtext(employee_name)::bigint) as employee_key,
    employee_name
from combined

union all

select 0::bigint, 'UNKNOWN'
