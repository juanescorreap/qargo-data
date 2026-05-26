with dates as (
    select generate_series(
        '2024-07-01'::date,
        (current_date + interval '3 years')::date,
        '1 day'::interval
    )::date as date
)

select
    to_char(date, 'YYYYMMDD')::integer                     as date_key,
    date,
    extract(isodow from date)::integer                     as day_of_week,
    trim(to_char(date, 'Day'))                             as day_name,
    extract(week    from date)::integer                    as week_number,
    extract(month   from date)::integer                    as month,
    trim(to_char(date, 'Month'))                           as month_name,
    extract(quarter from date)::integer                    as quarter,
    extract(year    from date)::integer                    as year,
    extract(isodow  from date) in (6, 7)                   as is_weekend
from dates
