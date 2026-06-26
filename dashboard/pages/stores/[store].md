---
title: '{params.store}'
---

```sql store_kpis
-- C1 cutover: avg_ticket from fact_order (additive order count)
select
    round(sum(f.order_net_sales)::numeric, 2)                                               as net_sales_cm,
    round((sum(f.order_net_sales) / nullif(sum(f.order_count), 0))::numeric, 2)             as avg_ticket_cm
from gold.fact_order f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and s.store_name = '${params.store}'
```

```sql store_kpi_ytd
select
    round(sum(f.net_sales)::numeric, 2) as net_sales_ytd
from gold.fact_sales f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where d.year = extract(year from current_date)::int
  and s.store_name = '${params.store}'
```

<BigValue data={store_kpis}    value=net_sales_cm  title="Net Sales, This Month" fmt=usd />
<BigValue data={store_kpis}    value=avg_ticket_cm title="Avg Ticket, This Month" fmt=usd />
<BigValue data={store_kpi_ytd} value=net_sales_ytd title="Net Sales, YTD"         fmt=usd />

---

```sql last_7_days
select
    d.date,
    round(sum(f.order_net_sales)::numeric, 2) as net_sales,
    sum(f.order_count)                        as order_count
from gold.fact_order f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where d.date >= (
    select max(d2.date) - interval '6 days'
    from gold.dim_date d2
    join gold.fact_order f2 on d2.date_key = f2.date_key
    join gold.dim_store  s2 on f2.store_key = s2.store_key
    where s2.store_name = '${params.store}'
)
  and s.store_name = '${params.store}'
group by d.date
order by d.date
```

## Last 7 Days

<LineChart
    data={last_7_days}
    x=date
    y=net_sales
    title="Daily Net Sales, L-7D"
    yFmt=usd
/>

---

```sql dow_heatmap
select
    d.day_name                                                    as day_of_week,
    d.day_of_week                                                 as dow_num,
    d.month_name                                                  as month_name,
    d.month                                                       as month_num,
    d.year                                                        as year,
    d.year || ' ' || d.month_name                                 as period,
    round(avg(daily.net_sales)::numeric, 2)                      as avg_daily_sales,
    round(avg(daily.order_count)::numeric, 1)                    as avg_orders
from (
    select
        f.date_key,
        sum(f.order_net_sales) as net_sales,
        sum(f.order_count)     as order_count
    from gold.fact_order f
    join gold.dim_store  s on f.store_key = s.store_key
    where s.store_name = '${params.store}'
    group by f.date_key
) daily
join gold.dim_date d on daily.date_key = d.date_key
where d.date >= current_date - interval '1 year'
group by d.day_name, d.day_of_week, d.month_name, d.month, d.year
order by d.year, d.month, d.day_of_week
```

## Sales Heatmap by Day of Week & Month (L-12M)

<Heatmap
    data={dow_heatmap}
    x=day_of_week
    y=period
    value=avg_daily_sales
    xSort=dow_num
    title="Avg Daily Sales — Day of Week × Month"
    valueFmt=usd
    borders=true
/>

---

```sql category_mix
select
    p.revenue_center_name,
    round(sum(f.net_sales)::numeric, 2)                                                       as net_sales,
    round(sum(f.net_sales) / sum(sum(f.net_sales)) over () * 100, 1)                          as pct_of_total
from gold.fact_sales f
join gold.dim_store   s on f.store_key   = s.store_key
join gold.dim_product p on f.product_key = p.product_key
join gold.dim_date    d on f.date_key    = d.date_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and s.store_name = '${params.store}'
  and p.revenue_center_name in ('Beverage','Food','Retail')
group by p.revenue_center_name
order by net_sales desc
```

## Category Mix — This Month

<BarChart
    data={category_mix}
    x=revenue_center_name
    y=pct_of_total
    title="Beverage vs Food vs Retail (% of Sales)"
    labels=true
/>

<DataTable data={category_mix}>
    <Column id=revenue_center_name title="Category"        />
    <Column id=net_sales           title="Net Sales" fmt=usd />
    <Column id=pct_of_total        title="% of Total"      />
</DataTable>

---

```sql channels_this_store
-- C1 cutover: fact_order (order count + avg_ticket by channel for this store)
select
    dest.channel,
    round(sum(f.order_net_sales)::numeric, 2)                                    as net_sales,
    sum(f.order_count)                                                           as order_count,
    round((sum(f.order_net_sales) / nullif(sum(f.order_count), 0))::numeric, 2)  as avg_ticket
from gold.fact_order f
join gold.dim_store       s    on f.store_key       = s.store_key
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date        d    on f.date_key        = d.date_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and s.store_name = '${params.store}'
  and dest.channel <> 'Unknown'
group by dest.channel
order by net_sales desc
```

## Top Channels — This Month

<BarChart
    data={channels_this_store}
    x=channel
    y=net_sales
    title="Net Sales by Channel"
    yFmt=usd
    sort=true
/>

<DataTable data={channels_this_store}>
    <Column id=channel     title="Channel"           />
    <Column id=net_sales   title="Net Sales" fmt=usd />
    <Column id=order_count title="Orders"            />
    <Column id=avg_ticket  title="Avg Ticket" fmt=usd />
</DataTable>

---

```sql top_employees_store
select
    e.employee_name,
    round(sum(f.net_sales)::numeric, 2)  as net_sales,
    sum(f.order_count)                   as order_count,
    round(avg(f.avg_ticket)::numeric, 2) as avg_ticket
from gold.fact_sales_by_employee f
join gold.dim_store    s on f.store_key    = s.store_key
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_date     d on f.date_key     = d.date_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and s.store_name    = '${params.store}'
  and e.employee_name <> 'UNKNOWN'
group by e.employee_name
order by net_sales desc
limit 15
```

## Top Employees — This Month

<DataTable data={top_employees_store}>
    <Column id=employee_name title="Employee"           />
    <Column id=net_sales     title="Net Sales" fmt=usd  />
    <Column id=order_count   title="Orders"             />
    <Column id=avg_ticket    title="Avg Ticket" fmt=usd />
</DataTable>
