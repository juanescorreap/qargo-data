---
title: Qargo Coffee — Operations & Finance
---

```sql employee_productivity
select
    e.employee_name,
    s.store_name,
    round(sum(f.net_sales)::numeric, 2)                                                               as net_sales,
    sum(f.order_count)                                                                                 as order_count,
    round(avg(f.avg_ticket)::numeric, 2)                                                              as avg_ticket,
    round(sum(f.tip_amount)::numeric, 2)                                                              as tip_amount,
    round((sum(f.tip_amount)    / nullif(sum(f.net_sales), 0) * 100)::numeric, 2)                     as tip_pct,
    round(sum(f.discount_total)::numeric, 2)                                                          as discount_total,
    round((sum(f.discount_total) / nullif(sum(f.net_sales + f.discount_total), 0) * 100)::numeric, 2) as discount_pct
from gold.fact_sales_by_employee f
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_store    s on f.store_key    = s.store_key
join gold.dim_date     d on f.date_key     = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales_by_employee f2 on d2.date_key = f2.date_key
)
and e.employee_name <> 'UNKNOWN'
group by e.employee_name, s.store_name
order by net_sales desc
```

```sql tip_distribution
select
    e.employee_name,
    s.store_name,
    round(sum(f.tip_amount)::numeric, 2)                                          as tip_amount,
    round((sum(f.tip_amount) / nullif(sum(f.net_sales), 0) * 100)::numeric, 2)   as tip_pct,
    sum(f.order_count)                                                            as order_count
from gold.fact_sales_by_employee f
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_store    s on f.store_key    = s.store_key
join gold.dim_date     d on f.date_key     = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales_by_employee f2 on d2.date_key = f2.date_key
)
and e.employee_name <> 'UNKNOWN'
and f.tip_amount > 0
group by e.employee_name, s.store_name
order by tip_pct desc
limit 20
```

```sql discount_audit
select
    e.employee_name,
    s.store_name,
    round(sum(f.discount_total)::numeric, 2)                                                          as discount_total,
    round((sum(f.discount_total) / nullif(sum(f.net_sales + f.discount_total), 0) * 100)::numeric, 2) as discount_pct,
    round(sum(f.net_sales)::numeric, 2)                                                               as net_sales
from gold.fact_sales_by_employee f
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_store    s on f.store_key    = s.store_key
join gold.dim_date     d on f.date_key     = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales_by_employee f2 on d2.date_key = f2.date_key
)
and e.employee_name <> 'UNKNOWN'
and f.discount_total > 0
group by e.employee_name, s.store_name
order by discount_pct desc
limit 20
```

```sql tax_by_store
select
    s.store_name,
    round(sum(f.tax_amount)::numeric, 2)                                                 as tax_amount,
    round(sum(f.net_sales)::numeric, 2)                                                  as net_sales,
    round((sum(f.tax_amount) / nullif(sum(f.net_sales), 0) * 100)::numeric, 2)           as effective_tax_rate
from gold.fact_sales f
join gold.dim_store s on f.store_key = s.store_key
join gold.dim_date  d on f.date_key  = d.date_key
where d.year = extract(year from current_date)::int
group by s.store_name
order by tax_amount desc
```

```sql financial_summary
select
    d.year || '-' || lpad(d.month::text, 2, '0')                          as year_month,
    round(sum(f.net_sales)::numeric, 2)                                    as net_sales,
    round((sum(f.net_sales) + sum(f.discount_total))::numeric, 2)          as gross_sales,
    round(sum(f.discount_total)::numeric, 2)                               as discount_total,
    round(sum(f.tax_amount)::numeric, 2)                                   as tax_amount,
    round(sum(f.tip_amount)::numeric, 2)                                   as tip_amount,
    round((sum(f.discount_total) / nullif(sum(f.net_sales + f.discount_total), 0) * 100)::numeric, 2) as discount_pct,
    round((sum(f.tip_amount) / nullif(sum(f.net_sales), 0) * 100)::numeric, 2)                        as tip_pct
from gold.fact_sales f
join gold.dim_date d on f.date_key = d.date_key
group by d.year, d.month
order by d.year, d.month
```

```sql source_system_comparison
select * from gold.source_summary
```

## Employee Productivity — This Month

<DataTable data={employee_productivity} />

## Tip Distribution — Top 20 This Month

<BarChart
    data={tip_distribution}
    x=employee_name
    y=tip_pct
    title="Tip % by Employee"
    sort=true
/>

<DataTable data={tip_distribution} />

## Discount Audit — This Month

<BarChart
    data={discount_audit}
    x=employee_name
    y=discount_pct
    title="Discount % by Employee (flag unusually high)"
    sort=true
/>

<DataTable data={discount_audit} />

## Tax Burden by Store — YTD

<DataTable data={tax_by_store} />

## Financial Summary by Month

<DataTable data={financial_summary} />

<LineChart
    data={financial_summary}
    x=year_month
    y={["net_sales", "gross_sales", "discount_total"]}
    title="Net Sales vs Gross Sales vs Discounts"
/>

## Data Lineage — PAR vs LS2

<DataTable
    data={source_system_comparison}
    title="Records and null fields by source system"
/>
