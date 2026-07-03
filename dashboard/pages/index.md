---
title: Executive Overview
---

_Executive Overview — brand-wide totals across all stores. Use the Store Directory below to drill into a specific location._

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
-- Anchor to the latest month WITH data (data ends 2026-06-30), not current_date.
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2 join gold.fact_order f2 on d2.date_key = f2.date_key
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
```

```sql kpi_items_current_month
-- C2 cutover: real Items Sold = sum(qty), net of returns, from fact_sale_item
select sum(f.qty) as items_sold
from gold.fact_sale_item f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
-- Anchor to the latest month WITH data (data ends 2026-06-30), not current_date.
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2 join gold.fact_sale_item f2 on d2.date_key = f2.date_key
  )
```

```sql kpi_items_ytd
select sum(f.qty) as items_sold_ytd
from gold.fact_sale_item f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where d.year = extract(year from current_date)::int
  and d.date <= current_date
```

## Current Month

<BigValue data={kpi_current_month}    value=net_sales   title="Net Sales"       fmt=usd  />
<BigValue data={kpi_current_month}    value=avg_ticket  title="Avg Ticket"      fmt=usd  />
<BigValue data={kpi_items_current_month} value=items_sold title="Items Sold (net of returns)" fmt=num0 />

## Year to Date

<BigValue data={kpi_ytd}           value=net_sales_ytd   title="Net Sales YTD"   fmt=usd />
<BigValue data={kpi_ytd}           value=avg_ticket_ytd  title="Avg Ticket YTD"  fmt=usd />
<BigValue data={kpi_items_ytd}     value=items_sold_ytd  title="Items Sold YTD (net of returns)" fmt=num0 />

---

```sql daily_last_90
-- Migrated off deprecated fact_sales to fact_order (order-level net sales).
select
    d.date,
    sum(f.order_net_sales) as net_sales
from gold.fact_order f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where d.date >= (
    select max(d2.date) - interval '89 days'
    from gold.dim_date d2
    join gold.fact_order f2 on d2.date_key = f2.date_key
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

```sql net_sales_ytd_daily
-- Cumulative (running) net sales for the year-to-date, anchored to the latest year WITH
-- data (data ends 2026-06-30). Global (all stores) — Executive Overview shows brand totals.
with daily as (
    select
        d.date,
        sum(f.order_net_sales) as net_sales
    from gold.fact_order f
    join gold.dim_date  d on f.date_key  = d.date_key
    where d.year = (
        select extract(year from max(d2.date))::int
        from gold.dim_date d2 join gold.fact_order f2 on d2.date_key = f2.date_key
      )
    group by d.date
)
select
    date,
    round(net_sales::numeric, 2)                                  as net_sales,
    round((sum(net_sales) over (order by date))::numeric, 2)      as cumulative_net_sales
from daily
order by date
```

## Cumulative Net Sales — YTD

<LineChart
    data={net_sales_ytd_daily}
    x=date
    y=cumulative_net_sales
    title="Cumulative Net Sales (Year to Date)"
    yFmt=usd
/>

---

```sql store_leaderboard_mom
with anchor as (
    -- Latest month WITH data (data ends 2026-06-30) — replaces current_date so the
    -- "This Month" column and MoM% are not empty in the July-vs-June gap.
    select date_trunc('month', max(d.date)) as m
    from gold.dim_date d join gold.fact_order f on d.date_key = f.date_key
),
monthly as (
    select
        s.store_name,
        date_trunc('month', d.date) as month_start,
        sum(f.order_net_sales) as net_sales
    from gold.fact_order f
    join gold.dim_date  d on f.date_key  = d.date_key
    join gold.dim_store s on f.store_key = s.store_key
    where date_trunc('month', d.date) >= (select m from anchor) - interval '1 month'
    group by s.store_name, date_trunc('month', d.date)
),
pivoted as (
    select
        store_name,
        sum(net_sales) filter (where month_start = (select m from anchor))                  as current_month,
        sum(net_sales) filter (where month_start = (select m from anchor) - interval '1 month') as prev_month
    from monthly
    group by store_name
)
select
    store_name,
    '/stores/' || store_name          as store_url,
    round(current_month::numeric, 2)  as current_month_sales,
    round(prev_month::numeric, 2)     as prev_month_sales,
    round(
        ((current_month - prev_month) / nullif(prev_month, 0))::numeric, 4
    )                                  as mom_growth_pct
from pivoted
order by mom_growth_pct desc nulls last
```

## Store Directory — Month-over-Month Growth

<DataTable data={store_leaderboard_mom} link=store_url rows=30 title="Click a store to open its detail page">
    <Column id=store_name          title="Store"                    />
    <Column id=current_month_sales title="This Month"       fmt=usd  />
    <Column id=prev_month_sales    title="Prev Month"       fmt=usd  />
    <Column id=mom_growth_pct      title="MoM Growth %"     fmt=pct1 />
</DataTable>

---

## Net Sales by Store — All Periods

```sql store_month_matrix
-- Pivot: one row per store, one column per month (net sales). DuckDB PIVOT wrapped in a
-- SELECT subquery so Evidence runs it as a normal query. Month columns are YYYY-MM, which
-- sort chronologically as text.
select *
from (
    pivot (
        select
            s.store_name,
            d.year || '-' || lpad(d.month::text, 2, '0') as year_month,
            f.order_net_sales
        from gold.fact_order f
        join gold.dim_date  d on f.date_key  = d.date_key
        join gold.dim_store s on f.store_key = s.store_key
    )
    on year_month
    using sum(order_net_sales)
    group by store_name
)
order by store_name
```

<DataTable data={store_month_matrix} rows=20 />

---

### Store Drill-down

```sql store_month_options
-- distinct store list for the dropdown (all stores, alphabetical)
select store_name from gold.dim_store order by store_name
```

<Dropdown
    data={store_month_options}
    name=store_filter_2
    value=store_name
    title="Store"
    defaultValue="TAMPA, FL"
/>

```sql store_monthly_sales
-- Net sales per month for the selected store (all available months).
select
    s.store_name,
    date_trunc('month', d.date)::date               as month,
    d.year || '-' || lpad(d.month::text, 2, '0')   as year_month,
    round(sum(f.order_net_sales)::numeric, 2)       as net_sales
from gold.fact_order f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where s.store_name = '${inputs.store_filter_2.value}'
group by s.store_name, date_trunc('month', d.date), d.year, d.month
order by month
```

<LineChart
    data={store_monthly_sales}
    x=month
    y=net_sales
    title="Monthly Net Sales — {inputs.store_filter_2.value}"
    yFmt=usd
/>

<DataTable data={store_monthly_sales} rows=24>
    <Column id=year_month title="Month"                />
    <Column id=net_sales  title="Net Sales"   fmt=usd  />
</DataTable>

---

```sql labor_efficiency
-- Rehabilitated via fact_by_employee (per employee/store/day grain). Score = named
-- net sales / active named employees. employee_key = 0 (UNKNOWN: PAR API numeric IDs
-- + unmapped staff) is excluded from both numerator and the employee count.
select
    s.store_name,
    round(sum(fbe.net_sales) filter (where fbe.employee_key <> 0)::numeric, 2)          as net_sales,
    count(distinct fbe.employee_key) filter (where fbe.employee_key <> 0)               as active_employees,
    round((sum(fbe.net_sales) filter (where fbe.employee_key <> 0)
           / nullif(count(distinct fbe.employee_key) filter (where fbe.employee_key <> 0), 0))::numeric, 2)
                                                                                        as sales_per_employee
from gold.fact_by_employee fbe
join gold.dim_store s on fbe.store_key = s.store_key
join gold.dim_date  d on fbe.date_key  = d.date_key
-- Anchor to the latest month WITH data (data ends 2026-06-30), not current_date.
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2 join gold.fact_by_employee f2 on d2.date_key = f2.date_key
  )group by s.store_name
order by sales_per_employee desc nulls last
```

## Labor Efficiency — Current Month

> Excludes PAR API rows (employee unknown). Score = net sales per active named employee.

<DataTable data={labor_efficiency} rows=20>
    <Column id=store_name         title="Store"                    />
    <Column id=net_sales          title="Net Sales"        fmt=usd />
    <Column id=active_employees   title="Active Employees"         />
    <Column id=sales_per_employee title="Sales / Employee" fmt=usd />
</DataTable>

---

```sql royalties_current_month
select
    s.store_name,
    s.royalty_rate,
    round(sum(f.order_net_sales)::numeric, 2)                      as net_sales,
    round(sum(f.order_net_sales * s.royalty_rate)::numeric, 2)     as royalty_due
from gold.fact_order f
join gold.dim_store s on f.store_key = s.store_key
join gold.dim_date  d on f.date_key  = d.date_key
-- Anchor to the latest month WITH data (data ends 2026-06-30), not current_date.
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2 join gold.fact_order f2 on d2.date_key = f2.date_key
  )
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
