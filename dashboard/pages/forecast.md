---
title: 2026 Forecast
---

```sql monthly_pivot_2026
select
    s.store_name,
    round(sum(case when d.month = 1  then f.net_sales else 0 end)::numeric, 2) as jan,
    round(sum(case when d.month = 2  then f.net_sales else 0 end)::numeric, 2) as feb,
    round(sum(case when d.month = 3  then f.net_sales else 0 end)::numeric, 2) as mar,
    round(sum(case when d.month = 4  then f.net_sales else 0 end)::numeric, 2) as apr,
    round(sum(case when d.month = 5  then f.net_sales else 0 end)::numeric, 2) as may,
    round(sum(case when d.month = 6  then f.net_sales else 0 end)::numeric, 2) as jun,
    round(sum(case when d.month = 7  then f.net_sales else 0 end)::numeric, 2) as jul,
    round(sum(case when d.month = 8  then f.net_sales else 0 end)::numeric, 2) as aug,
    round(sum(case when d.month = 9  then f.net_sales else 0 end)::numeric, 2) as sep,
    round(sum(case when d.month = 10 then f.net_sales else 0 end)::numeric, 2) as oct,
    round(sum(case when d.month = 11 then f.net_sales else 0 end)::numeric, 2) as nov,
    round(sum(case when d.month = 12 then f.net_sales else 0 end)::numeric, 2) as dec,
    round(sum(f.net_sales)::numeric, 2)                                         as total
from gold.fact_sales f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where d.year = 2026
group by s.store_name
order by sum(f.net_sales) desc
```

```sql monthly_comparison
select
    d.month,
    d.month_name,
    cast(d.year as text)             as year,
    round(sum(f.net_sales)::numeric, 2) as net_sales
from gold.fact_sales f
join gold.dim_date d on f.date_key = d.date_key
where d.year in (2025, 2026)
group by d.month, d.month_name, d.year
order by d.month, d.year
```

## Monthly Sales by Store, 2026

<DataTable data={monthly_pivot_2026} />

## Monthly Sales, 2025 vs 2026

<BarChart
    data={monthly_comparison}
    x=month_name
    y=net_sales
    series=year
    title="Monthly Sales 2025 vs 2026"
/>
