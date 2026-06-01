---
title: Channels & Destinations
---

```sql channel_comparison
select
    dest.channel,
    round(sum(f.net_sales)::numeric, 2)                                         as net_sales,
    sum(f.order_count)                                                           as order_count,
    round(avg(f.avg_ticket)::numeric, 2)                                         as avg_ticket,
    round((sum(f.net_sales) / sum(sum(f.net_sales)) over () * 100)::numeric, 1) as pct_of_total
from gold.fact_sales f
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date         d   on f.date_key        = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
  and dest.channel <> 'Unknown'
group by dest.channel
order by net_sales desc
```

## Channel Performance — Most Recent Month

<BigValue
    data={channel_comparison}
    value=net_sales
    title="Top Channel Net Sales"
    fmt=usd
/>

<BarChart
    data={channel_comparison}
    x=channel
    y={["net_sales","avg_ticket"]}
    title="Net Sales and Avg Ticket by Channel"
    yFmt=usd
    sort=true
/>

<DataTable data={channel_comparison}>
    <Column id=channel      title="Channel"               />
    <Column id=net_sales    title="Net Sales"    fmt=usd  />
    <Column id=order_count  title="Orders"                />
    <Column id=avg_ticket   title="Avg Ticket"   fmt=usd  />
    <Column id=pct_of_total title="% of Total"            />
</DataTable>

---

```sql delivery_leakage
select
    d.year || '-' || lpad(d.month::text, 2, '0')                                                        as year_month,
    round(sum(f.net_sales)::numeric, 2)                                                                  as net_sales,
    round(sum(f.discount_total)::numeric, 2)                                                             as discount_total,
    round((sum(f.discount_total) / nullif(sum(f.net_sales + f.discount_total), 0) * 100)::numeric, 1)   as discount_pct
from gold.fact_sales f
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date         d   on f.date_key        = d.date_key
where dest.channel = 'Delivery'
group by d.year, d.month
order by d.year, d.month
```

## Delivery Leakage — Net Sales vs Discounts

<BarChart
    data={delivery_leakage}
    x=year_month
    y={["net_sales","discount_total"]}
    title="Delivery: Net Sales vs Discount Given"
    yFmt=usd
/>

<LineChart
    data={delivery_leakage}
    x=year_month
    y=discount_pct
    title="Delivery Discount % Over Time"
/>

---

```sql drivethu_monthly
select
    d.year || '-' || lpad(d.month::text, 2, '0')        as year_month,
    round(sum(f.net_sales)::numeric, 2)                  as net_sales,
    sum(f.order_count)                                   as order_count,
    round(avg(f.avg_ticket)::numeric, 2)                 as avg_ticket
from gold.fact_sales f
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date         d   on f.date_key        = d.date_key
where dest.channel = 'Drive-Thru'
group by d.year, d.month
order by d.year, d.month
```

## Drive-Thru Volume — Monthly

> Hourly throughput data will be available once the PAR API time-of-sale ingestion is active.

<BarChart
    data={drivethu_monthly}
    x=year_month
    y=order_count
    title="Drive-Thru Orders by Month"
    sort=false
/>

<LineChart
    data={drivethu_monthly}
    x=year_month
    y=net_sales
    title="Drive-Thru Net Sales by Month"
    yFmt=usd
/>

<DataTable data={drivethu_monthly}>
    <Column id=year_month  title="Month"               />
    <Column id=net_sales   title="Net Sales"   fmt=usd />
    <Column id=order_count title="Orders"              />
    <Column id=avg_ticket  title="Avg Ticket"  fmt=usd />
</DataTable>

---

```sql unknown_destination_trend
select
    d.year || '-' || lpad(d.month::text, 2, '0')                                                    as year_month,
    sum(case when dest.destination_key = 0 then f.order_count else 0 end)                           as unknown_orders,
    sum(f.order_count)                                                                               as total_orders,
    round(
        sum(case when dest.destination_key = 0 then f.order_count else 0 end)::numeric
        / nullif(sum(f.order_count), 0) * 100, 1
    )                                                                                                as unknown_pct
from gold.fact_sales f
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date         d   on f.date_key        = d.date_key
group by d.year, d.month
order by d.year, d.month
```

## Data Quality: Unknown Destination Monitor

<DataTable data={unknown_destination_trend} title="Unknown destination (key=0) over time" />
