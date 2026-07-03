---
title: Labor & Operations
---

<!--
Rehabilitated on the new gold.fact_by_employee model (per employee/store/day grain,
replaces the dropped fact_sales_by_employee). Two of the four tiles are fully restored;
Tip Performance and per-hour Shift Productivity stay disabled because the underlying
data does not exist in the POS feeds (tip_amount is a 0 literal, and there is no
time-of-sale / shift column in either source).

All figures cover the MOST RECENT MONTH present in the data and exclude the UNKNOWN
employee bucket (employee_key = 0: PAR API numeric IDs + unmapped staff).
-->

## Labor & Operations

```sql recent_month
select date_trunc('month', max(d.date)) as month_start
from gold.fact_by_employee fbe
join gold.dim_date d on fbe.date_key = d.date_key
```

---

## Up-selling Leaderboard — Highest Avg Ticket

Baristas ranked by average ticket — a proxy for successfully suggesting size upgrades,
modifiers, and food attachments.

```sql upselling_leaderboard
select
    e.employee_name,
    s.store_name,
    round(sum(fbe.net_sales)::numeric, 2)                                        as net_sales,
    sum(fbe.order_count)                                                         as orders,
    round((sum(fbe.net_sales) / nullif(sum(fbe.order_count), 0))::numeric, 2)    as avg_ticket
from gold.fact_by_employee fbe
join gold.dim_employee e on fbe.employee_key = e.employee_key
join gold.dim_store    s on fbe.store_key    = s.store_key
join gold.dim_date     d on fbe.date_key     = d.date_key
where fbe.employee_key <> 0
  and date_trunc('month', d.date) = (select month_start from ${recent_month})
group by e.employee_name, s.store_name
having sum(fbe.order_count) >= 20
order by avg_ticket desc
limit 20
```

> Excludes PAR API rows (employee unknown). Minimum 20 orders to qualify.

<DataTable data={upselling_leaderboard} rows=20>
    <Column id=employee_name title="Employee"           />
    <Column id=store_name    title="Store"              />
    <Column id=avg_ticket    title="Avg Ticket" fmt=usd />
    <Column id=orders        title="Orders"             />
    <Column id=net_sales     title="Net Sales"  fmt=usd />
</DataTable>

---

## Discount Audit Trail — Total Discounts Issued

Risk-mitigation view: employees ranked by absolute discount volume issued. A high
outlier can indicate systemic comp abuse, internal theft, or a training gap.

```sql discount_audit
select
    e.employee_name,
    s.store_name,
    round(sum(fbe.discount_total)::numeric, 2)                                          as discount_total,
    round(sum(fbe.net_sales)::numeric, 2)                                               as net_sales,
    round((sum(fbe.discount_total)
           / nullif(sum(fbe.net_sales + fbe.discount_total), 0) * 100)::numeric, 1)     as discount_pct
from gold.fact_by_employee fbe
join gold.dim_employee e on fbe.employee_key = e.employee_key
join gold.dim_store    s on fbe.store_key    = s.store_key
join gold.dim_date     d on fbe.date_key     = d.date_key
where fbe.employee_key <> 0
  and date_trunc('month', d.date) = (select month_start from ${recent_month})
group by e.employee_name, s.store_name
order by discount_total desc
limit 20
```

> Excludes PAR API rows (employee unknown). `Discount %` = discounts / gross (net + discount).

<DataTable data={discount_audit} rows=20>
    <Column id=employee_name  title="Employee"            />
    <Column id=store_name     title="Store"               />
    <Column id=discount_total title="Discounts"   fmt=usd />
    <Column id=net_sales      title="Net Sales"   fmt=usd />
    <Column id=discount_pct   title="Discount %"          />
</DataTable>

---

## Shift Productivity — Orders per Employee per Day

> Hourly shift data not available. Showing orders/employee/day as approximation.

```sql shift_productivity
-- No time-of-sale / clock-in data exists in either source, so per-HOUR productivity
-- is not derivable. Orders per active employee-DAY is the finest available proxy.
select
    s.store_name,
    sum(fbe.order_count)                                                              as total_orders,
    count(*)                                                                          as employee_days,
    round((sum(fbe.order_count)::numeric / nullif(count(*), 0)), 1)                   as orders_per_employee_day
from gold.fact_by_employee fbe
join gold.dim_store s on fbe.store_key = s.store_key
join gold.dim_date  d on fbe.date_key  = d.date_key
where fbe.employee_key <> 0
  and date_trunc('month', d.date) = (select month_start from ${recent_month})
group by s.store_name
order by orders_per_employee_day desc
```

<BarChart
    data={shift_productivity}
    x=store_name
    y=orders_per_employee_day
    title="Orders per Employee-Day by Store"
    sort=true
/>

<DataTable data={shift_productivity}>
    <Column id=store_name              title="Store"                 />
    <Column id=orders_per_employee_day title="Orders / Employee-Day" />
    <Column id=total_orders            title="Total Orders"          />
    <Column id=employee_days           title="Employee-Days"         />
</DataTable>

---

## Tip Performance Index

> Tip data not available in current POS integration.

_The PAR and LS2 feeds expose no tip amount, so the Tip / Net Sales index cannot be
computed. `fact_by_employee.tip_amount` is retained (always 0) for forward-compatibility
once a tip-carrying source is integrated._
