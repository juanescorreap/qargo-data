---
title: Labor & Operations
---

```sql date_filter_month
select date_trunc('month', current_date) as current_month
```

```sql upselling_leaderboard
select
    e.employee_name,
    s.store_name,
    round(sum(f.net_sales)::numeric, 2)   as net_sales,
    sum(f.order_count)                    as order_count,
    round(avg(f.avg_ticket)::numeric, 2)  as avg_ticket
from gold.fact_sales_by_employee f
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_store    s on f.store_key    = s.store_key
join gold.dim_date     d on f.date_key     = d.date_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and e.employee_name <> 'UNKNOWN'
group by e.employee_name, s.store_name
order by avg_ticket desc
limit 30
```

## Up-selling Leaderboard — Highest Avg Ticket This Month

<DataTable data={upselling_leaderboard} search=true rows=20>
    <Column id=employee_name title="Employee"           />
    <Column id=store_name    title="Store"              />
    <Column id=net_sales     title="Net Sales" fmt=usd  />
    <Column id=order_count   title="Orders"             />
    <Column id=avg_ticket    title="Avg Ticket" fmt=usd />
</DataTable>

<BarChart
    data={upselling_leaderboard}
    x=employee_name
    y=avg_ticket
    title="Avg Ticket by Employee (Top 30, This Month)"
    yFmt=usd
    swapXY=true
    sort=true
/>

---

```sql tip_performance
select
    e.employee_name,
    s.store_name,
    round(sum(f.tip_amount)::numeric, 2)                                                     as tip_amount,
    round(sum(f.net_sales)::numeric, 2)                                                      as net_sales,
    round((sum(f.tip_amount) / nullif(sum(f.net_sales), 0) * 100)::numeric, 2)              as tip_pct,
    sum(f.order_count)                                                                       as order_count
from gold.fact_sales_by_employee f
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_store    s on f.store_key    = s.store_key
join gold.dim_date     d on f.date_key     = d.date_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and e.employee_name <> 'UNKNOWN'
  and f.tip_amount > 0
group by e.employee_name, s.store_name
order by tip_pct desc
limit 20
```

## Tip Performance Index — This Month

<BarChart
    data={tip_performance}
    x=employee_name
    y=tip_pct
    title="Tip % by Employee (proxy for service quality)"
    swapXY=true
    sort=true
/>

<DataTable data={tip_performance} rows=20>
    <Column id=employee_name title="Employee"              />
    <Column id=store_name    title="Store"                 />
    <Column id=tip_amount    title="Tip Amount"   fmt=usd  />
    <Column id=net_sales     title="Net Sales"    fmt=usd  />
    <Column id=tip_pct       title="Tip %"                 />
    <Column id=order_count   title="Orders"                />
</DataTable>

---

```sql shift_productivity
select
    e.employee_name,
    s.store_name,
    sum(f.order_count)                                                               as total_orders,
    count(distinct d.date)                                                           as days_active,
    round((sum(f.order_count)::numeric / nullif(count(distinct d.date), 0)), 1)     as orders_per_day
from gold.fact_sales_by_employee f
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_store    s on f.store_key    = s.store_key
join gold.dim_date     d on f.date_key     = d.date_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and e.employee_name <> 'UNKNOWN'
group by e.employee_name, s.store_name
having count(distinct d.date) >= 3
order by orders_per_day desc
limit 30
```

## Shift Productivity — Orders per Active Day

<DataTable data={shift_productivity} rows=20>
    <Column id=employee_name  title="Employee"               />
    <Column id=store_name     title="Store"                  />
    <Column id=total_orders   title="Total Orders"           />
    <Column id=days_active    title="Days Active"            />
    <Column id=orders_per_day title="Orders / Day"           />
</DataTable>

---

```sql discount_audit
select
    e.employee_name,
    s.store_name,
    round(sum(f.discount_total)::numeric, 2)                                                         as discount_total,
    round(sum(f.net_sales)::numeric, 2)                                                              as net_sales,
    round((sum(f.discount_total) / nullif(sum(f.net_sales + f.discount_total), 0) * 100)::numeric, 2) as discount_pct
from gold.fact_sales_by_employee f
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_store    s on f.store_key    = s.store_key
join gold.dim_date     d on f.date_key     = d.date_key
where date_trunc('month', d.date) = date_trunc('month', current_date)
  and e.employee_name <> 'UNKNOWN'
  and f.discount_total > 0
group by e.employee_name, s.store_name
order by discount_pct desc
limit 20
```

## Discount Audit Trail — Flag Outliers

<BarChart
    data={discount_audit}
    x=employee_name
    y=discount_pct
    title="Discount % by Employee — This Month (higher = review needed)"
    swapXY=true
    sort=true
/>

<DataTable data={discount_audit} rows=20>
    <Column id=employee_name  title="Employee"                />
    <Column id=store_name     title="Store"                   />
    <Column id=discount_total title="Discount Total" fmt=usd  />
    <Column id=net_sales      title="Net Sales"      fmt=usd  />
    <Column id=discount_pct   title="Discount %"              />
</DataTable>
