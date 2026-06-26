---
title: Executive Overview
---

```sql store_list
select 'All Stores' as store_name, 0 as sort_order
union all
select store_name, 1 as sort_order from gold.dim_store
order by sort_order, store_name
```

<Dropdown
    name="store_filter"
    data={store_list}
    value="store_name"
    label="store_name"
    title="Store"
    defaultValue="All Stores"
/>

```sql kpi_current_month
-- C1 cutover: order_count + avg_ticket from fact_order (additive). net_sales here is
-- order-level (sums identically to fact_sales.net_sales).
select
    sum(f.order_net_sales)                                                              as net_sales,
    sum(f.order_count)                                                                  as order_count,
    round((sum(f.order_net_sales) / nullif(sum(f.order_count), 0))::numeric, 2)        as avg_ticket
from gold.fact_order f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and (
      '${inputs.store_filter}' = 'All Stores'
      or '${inputs.store_filter}' = ''
      or s.store_name = '${inputs.store_filter}'
  )
```

```sql kpi_ytd
-- C1 cutover: fact_order (additive order_count + avg_ticket)
select
    sum(f.order_net_sales)                                                              as net_sales_ytd,
    sum(f.order_count)                                                                  as order_count_ytd,
    round((sum(f.order_net_sales) / nullif(sum(f.order_count), 0))::numeric, 2)        as avg_ticket_ytd
from gold.fact_order f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where d.year = extract(year from current_date)::int
  and d.date <= current_date
  and (
      '${inputs.store_filter}' = 'All Stores'
      or '${inputs.store_filter}' = ''
      or s.store_name = '${inputs.store_filter}'
  )
```

```sql kpi_items_current_month
-- C2 cutover: real Items Sold = sum(qty), net of returns, from fact_sale_item
select sum(f.qty) as items_sold
from gold.fact_sale_item f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and (
      '${inputs.store_filter}' = 'All Stores'
      or '${inputs.store_filter}' = ''
      or s.store_name = '${inputs.store_filter}'
  )
```

```sql kpi_items_ytd
select sum(f.qty) as items_sold_ytd
from gold.fact_sale_item f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where d.year = extract(year from current_date)::int
  and d.date <= current_date
  and (
      '${inputs.store_filter}' = 'All Stores'
      or '${inputs.store_filter}' = ''
      or s.store_name = '${inputs.store_filter}'
  )
```

## Current Month

<BigValue data={kpi_current_month}    value=net_sales   title="Net Sales"       fmt=usd  />
<BigValue data={kpi_current_month}    value=avg_ticket  title="Avg Ticket"      fmt=usd  />
<BigValue data={kpi_items_current_month} value=items_sold title="Items Sold (net of returns)" />

## Year to Date

<BigValue data={kpi_ytd}           value=net_sales_ytd   title="Net Sales YTD"   fmt=usd />
<BigValue data={kpi_ytd}           value=avg_ticket_ytd  title="Avg Ticket YTD"  fmt=usd />
<BigValue data={kpi_items_ytd}     value=items_sold_ytd  title="Items Sold YTD (net of returns)" />

---

```sql daily_last_90
select
    d.date,
    sum(f.net_sales) as net_sales
from gold.fact_sales f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where d.date >= (
    select max(d2.date) - interval '89 days'
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
  and (
      '${inputs.store_filter}' = 'All Stores'
      or '${inputs.store_filter}' = ''
      or s.store_name = '${inputs.store_filter}'
  )
group by d.date
order by d.date
```

## Daily Net Sales — Last 90 Days

<AreaChart
    data={daily_last_90}
    x=date
    y=net_sales
    title="Daily Net Sales (Last 90 Days)"
    yFmt=usd
/>

---

```sql store_leaderboard_mom
with monthly as (
    select
        s.store_name,
        date_trunc('month', d.date) as month_start,
        sum(f.net_sales) as net_sales
    from gold.fact_sales f
    join gold.dim_date  d on f.date_key  = d.date_key
    join gold.dim_store s on f.store_key = s.store_key
    where date_trunc('month', d.date) >= date_trunc('month', current_date) - interval '1 month'
    group by s.store_name, date_trunc('month', d.date)
),
pivoted as (
    select
        store_name,
        sum(net_sales) filter (where month_start = date_trunc('month', current_date))                  as current_month,
        sum(net_sales) filter (where month_start = date_trunc('month', current_date) - interval '1 month') as prev_month
    from monthly
    group by store_name
)
select
    store_name,
    round(current_month::numeric, 2)  as current_month_sales,
    round(prev_month::numeric, 2)     as prev_month_sales,
    round(
        ((current_month - prev_month) / nullif(prev_month, 0) * 100)::numeric, 1
    )                                  as mom_growth_pct
from pivoted
order by mom_growth_pct desc nulls last
```

## Store Leaderboard — Month-over-Month Growth

```sql store_links
select
    store_name,
    '/stores/' || store_name   as store_url
from gold.dim_store
order by store_name
```

<DataTable data={store_links} link=store_url title="Store Directory" rows=30 />

<DataTable
    data={store_leaderboard_mom}
    rows=20
>
    <Column id=store_name      title="Store"             />
    <Column id=current_month_sales title="This Month"   fmt=usd />
    <Column id=prev_month_sales    title="Prev Month"   fmt=usd />
    <Column id=mom_growth_pct      title="MoM Growth %"         />
</DataTable>

---

```sql labor_efficiency
with employee_counts as (
    select
        s.store_name,
        count(distinct e.employee_key) filter (where e.employee_name <> 'UNKNOWN') as active_employees
    from gold.fact_sales_by_employee f
    join gold.dim_store    s on f.store_key    = s.store_key
    join gold.dim_employee e on f.employee_key = e.employee_key
    join gold.dim_date     d on f.date_key     = d.date_key
    where date_trunc('month', d.date) = date_trunc('month', current_date)
    group by s.store_name
),
store_sales as (
    select
        s.store_name,
        sum(f.net_sales) as net_sales
    from gold.fact_sales f
    join gold.dim_store s on f.store_key = s.store_key
    join gold.dim_date  d on f.date_key  = d.date_key
    where date_trunc('month', d.date) = date_trunc('month', current_date)
    group by s.store_name
)
select
    ss.store_name,
    round(ss.net_sales::numeric, 2)                                                as net_sales,
    ec.active_employees,
    round((ss.net_sales / nullif(ec.active_employees, 0))::numeric, 2)             as sales_per_employee
from store_sales ss
join employee_counts ec on ss.store_name = ec.store_name
order by sales_per_employee desc
```

## Labor Efficiency — Current Month

<DataTable data={labor_efficiency} rows=20>
    <Column id=store_name         title="Store"               />
    <Column id=net_sales          title="Net Sales"   fmt=usd />
    <Column id=active_employees   title="Active Staff"        />
    <Column id=sales_per_employee title="Sales / Employee" fmt=usd />
</DataTable>

---

```sql royalties_current_month
select
    s.store_name,
    s.royalty_rate,
    round(sum(f.net_sales)::numeric, 2)                            as net_sales,
    round(sum(f.net_sales * s.royalty_rate)::numeric, 2)           as royalty_due
from gold.fact_sales f
join gold.dim_store s on f.store_key = s.store_key
join gold.dim_date  d on f.date_key  = d.date_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
group by s.store_name, s.royalty_rate
order by royalty_due desc
```

## Estimated Royalties — Current Month

<DataTable data={royalties_current_month} rows=20>
    <Column id=store_name   title="Store"               />
    <Column id=royalty_rate title="Rate"   fmt=pct1     />
    <Column id=net_sales    title="Net Sales"   fmt=usd />
    <Column id=royalty_due  title="Royalty Due" fmt=usd />
</DataTable>
