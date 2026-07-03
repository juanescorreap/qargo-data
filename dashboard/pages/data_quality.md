---
title: Data Quality & Reconciliation
---

```sql source_reconciliation
select
    _source_system    as source,
    order_count,
    row_count,
    net_sales,
    round(net_sales / nullif(row_count, 0), 2)  as avg_net_sales_per_row,
    tax_amount,
    discount_total,
    null_destination,
    null_employee
from source_summary
order by net_sales desc
```

```sql source_by_month_data
select source, year_month, net_sales, order_count
from source_by_month
order by year_month, source
```

## Source Reconciliation — PAR vs LS2

<BigValue data={source_reconciliation} value=net_sales    title="Total Net Sales"    fmt=usd />
<BigValue data={source_reconciliation} value=order_count  title="Total Orders"               />
<BigValue data={source_reconciliation} value=row_count    title="Total Rows Ingested"        />

<BarChart
    data={source_reconciliation}
    x=source
    y=net_sales
    title="Total Net Sales by Source System"
    yFmt=usd
/>

<BarChart
    data={source_by_month_data}
    x=year_month
    y=net_sales
    series=source
    title="Monthly Net Sales by Source System"
    yFmt=usd
/>

<DataTable data={source_reconciliation} title="All-Time Totals by Source">
    <Column id=source               title="Source"                    />
    <Column id=net_sales            title="Net Sales"        fmt=usd  />
    <Column id=order_count          title="Orders"                    />
    <Column id=row_count            title="Rows"                      />
    <Column id=avg_net_sales_per_row title="Avg $ per Row"   fmt=usd  />
</DataTable>

---

```sql unknown_employee_by_month
-- Rehabilitated via gold.fact_by_employee. Tracks the share of net sales attributed to
-- UNKNOWN staff (employee_key = 0: unmapped names + PAR API numeric IDs). A rising trend
-- signals an upstream fracture in employee-name ingestion.
select
    lpad(d.year::int::text, 4, '0') || '-' || lpad(d.month::int::text, 2, '0')                                            as year_month,
    round(sum(fbe.net_sales) filter (where fbe.employee_key = 0)::numeric, 2)                as unknown_net_sales,
    round(sum(fbe.net_sales)::numeric, 2)                                                    as total_net_sales,
    round((sum(fbe.net_sales) filter (where fbe.employee_key = 0)
           / nullif(sum(fbe.net_sales), 0))::numeric, 4)                                      as unknown_pct
from gold.fact_by_employee fbe
join gold.dim_date d on fbe.date_key = d.date_key
group by d.year, d.month
order by d.year, d.month
```

```sql unknown_employee_by_store
-- Same metric by store for the most recent month in the data.
select
    s.store_name,
    round(sum(fbe.net_sales) filter (where fbe.employee_key = 0)::numeric, 2)                as unknown_net_sales,
    round(sum(fbe.net_sales)::numeric, 2)                                                    as total_net_sales,
    round((sum(fbe.net_sales) filter (where fbe.employee_key = 0)
           / nullif(sum(fbe.net_sales), 0))::numeric, 4)                                      as unknown_pct
from gold.fact_by_employee fbe
join gold.dim_store s on fbe.store_key = s.store_key
join gold.dim_date  d on fbe.date_key  = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.fact_by_employee f2
    join gold.dim_date d2 on f2.date_key = d2.date_key
)
group by s.store_name
order by unknown_pct desc nulls last
```

```sql unknown_destination
select
    lpad(d.year::int::text, 4, '0') || '-' || lpad(d.month::int::text, 2, '0')                                      as year_month,
    sum(case when f.destination_key = 0 then f.order_count else 0 end)                as unknown_dest_orders,
    sum(f.order_count)                                                                  as total_orders,
    round(
        sum(case when f.destination_key = 0 then f.order_count else 0 end)::numeric
        / nullif(sum(f.order_count), 0), 4
    )                                                                                   as unknown_pct
from gold.fact_order f
join gold.dim_date d on f.date_key = d.date_key
group by d.year, d.month
order by d.year, d.month
```

```sql unknown_totals
select
    (select count(*) from gold.dim_employee where employee_name = 'UNKNOWN')    as unknown_employee_rows,
    (select sum(order_count) from gold.fact_order where destination_key = 0)     as unknown_dest_orders
```

## Unknown Tracker

<BigValue data={unknown_totals} value=unknown_employee_rows title="UNKNOWN Employee Rows in dim_employee" />
<BigValue data={unknown_totals} value=unknown_dest_orders   title="Orders with Unknown Destination (all time)" />

### UNKNOWN Employee — % of Net Sales

> Share of net sales booked to UNKNOWN staff (`employee_key = 0`: unmapped names + PAR
> API numeric IDs). A rising trend flags an upstream employee-name ingestion fracture.

<LineChart
    data={unknown_employee_by_month}
    x=year_month
    y=unknown_pct
    yFmt=pct1
    title="% Net Sales with Unknown Employee — Monthly"
/>

<DataTable data={unknown_employee_by_store} title="Unknown Employee by Store — Most Recent Month">
    <Column id=store_name        title="Store"                    />
    <Column id=unknown_net_sales title="Unknown Net Sales" fmt=usd />
    <Column id=total_net_sales   title="Total Net Sales"   fmt=usd />
    <Column id=unknown_pct       title="Unknown %"        fmt=pct1 />
</DataTable>

---

### Unknown Destination — Monthly

<LineChart
    data={unknown_destination}
    x=year_month
    y=unknown_pct
    yFmt=pct1
    title="% Orders with Unknown Destination — Monthly"
/>

<DataTable data={unknown_destination}  title="Unknown Destination by Month" />

---

```sql freshness_monitor
select source_name, filename, row_count, loaded_at
from freshness_data
order by loaded_at desc
limit 20
```

```sql freshness_summary
select
    source_name,
    max(loaded_at)  as last_loaded_at,
    sum(row_count)  as total_rows_ingested,
    count(*)        as files_processed
from freshness_data
group by source_name
order by last_loaded_at desc
```

```sql data_watermark
select
    max(d.date)                                            as latest_sale_date,
    min(d.date)                                            as earliest_sale_date,
    datediff('day', max(d.date), current_date)             as days_since_last_data
from gold.fact_order f
join gold.dim_date d on f.date_key = d.date_key
```

## Freshness Monitor

<BigValue data={data_watermark} value=latest_sale_date   title="Latest Sale Date in Pipeline" />
<BigValue data={data_watermark} value=days_since_last_data title="Days Since Last Data"        />

<DataTable data={freshness_summary} title="Ingestion Summary by Source">
    <Column id=source_name         title="Source"              />
    <Column id=last_loaded_at      title="Last Loaded At"      />
    <Column id=total_rows_ingested title="Total Rows"          />
    <Column id=files_processed     title="Files Processed"     />
</DataTable>

<DataTable data={freshness_monitor} title="Most Recent 20 Processed Files">
    <Column id=source_name title="Source"    />
    <Column id=filename    title="File"      />
    <Column id=row_count   title="Rows"      />
    <Column id=loaded_at   title="Loaded At" />
</DataTable>
