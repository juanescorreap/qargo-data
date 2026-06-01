---
title: Data Quality & Reconciliation
---

```sql source_reconciliation
select
    _source_system    as source,
    order_count,
    net_sales,
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

```sql unknown_employees
select
    d.year || '-' || lpad(d.month::text, 2, '0')                                      as year_month,
    sum(case when e.employee_name = 'UNKNOWN' then f.order_count else 0 end)           as unknown_employee_orders,
    sum(f.order_count)                                                                  as total_orders,
    round(
        sum(case when e.employee_name = 'UNKNOWN' then f.order_count else 0 end)::numeric
        / nullif(sum(f.order_count), 0) * 100, 1
    )                                                                                   as unknown_pct
from gold.fact_sales_by_employee f
join gold.dim_employee e on f.employee_key = e.employee_key
join gold.dim_date     d on f.date_key     = d.date_key
group by d.year, d.month
order by d.year, d.month
```

```sql unknown_destination
select
    d.year || '-' || lpad(d.month::text, 2, '0')                                      as year_month,
    sum(case when f.destination_key = 0 then f.order_count else 0 end)                as unknown_dest_orders,
    sum(f.order_count)                                                                  as total_orders,
    round(
        sum(case when f.destination_key = 0 then f.order_count else 0 end)::numeric
        / nullif(sum(f.order_count), 0) * 100, 1
    )                                                                                   as unknown_pct
from gold.fact_sales f
join gold.dim_date d on f.date_key = d.date_key
group by d.year, d.month
order by d.year, d.month
```

```sql unknown_totals
select
    (select count(*) from gold.dim_employee where employee_name = 'UNKNOWN')    as unknown_employee_rows,
    (select sum(order_count) from gold.fact_sales where destination_key = 0)     as unknown_dest_orders
```

## Unknown Tracker

<BigValue data={unknown_totals} value=unknown_employee_rows title="UNKNOWN Employee Rows in dim_employee" />
<BigValue data={unknown_totals} value=unknown_dest_orders   title="Orders with Unknown Destination (all time)" />

<LineChart
    data={unknown_employees}
    x=year_month
    y=unknown_pct
    title="% Orders with UNKNOWN Employee — Monthly"
/>

<LineChart
    data={unknown_destination}
    x=year_month
    y=unknown_pct
    title="% Orders with Unknown Destination — Monthly"
/>

<DataTable data={unknown_employees}    title="Unknown Employee by Month"    />
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
from fact_sales f
join dim_date d on f.date_key = d.date_key
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
