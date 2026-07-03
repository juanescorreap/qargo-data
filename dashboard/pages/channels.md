---
title: Channels & Destinations
---

```sql channel_comparison
-- C1 cutover: order_count + avg_ticket from fact_order (has destination_key). avg_ticket
-- recomputed as net/orders (the old avg(avg_ticket) was itself a grain-average artifact).
select
    dest.channel,
    round(sum(f.order_net_sales)::numeric, 2)                                              as net_sales,
    sum(f.order_count)                                                                     as order_count,
    round((sum(f.order_net_sales) / nullif(sum(f.order_count), 0))::numeric, 2)            as avg_ticket,
    round((sum(f.order_net_sales) / sum(sum(f.order_net_sales)) over ())::numeric, 4) as pct_of_total
from gold.fact_order f
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date         d   on f.date_key        = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_order f2 on d2.date_key = f2.date_key
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
    y=net_sales
    title="Net Sales by Channel"
    yFmt=usd
    sort=true
/>

<BarChart
    data={channel_comparison}
    x=channel
    y=avg_ticket
    title="Avg Ticket by Channel"
    yFmt=usd
    sort=true
/>

<DataTable data={channel_comparison}>
    <Column id=channel      title="Channel"               />
    <Column id=net_sales    title="Net Sales"    fmt=usd  />
    <Column id=order_count  title="Orders"                />
    <Column id=avg_ticket   title="Avg Ticket"   fmt=usd  />
    <Column id=pct_of_total title="% of Total"   fmt=pct1 />
</DataTable>

---

```sql delivery_leakage
-- Rehabilitated via fact_order_detail (discount_total per order), JOINed 1:1 to
-- fact_order on (source_system, order_id). Exposes promo margin erosion on 3rd-party
-- delivery channels: net sales vs discounts issued.
select
    dest.destination_name,
    round(sum(f.order_net_sales)::numeric, 2)                                            as net_sales,
    round(sum(fod.discount_total)::numeric, 2)                                           as discount_total,
    round((sum(fod.discount_total)
           / nullif(sum(f.order_net_sales + fod.discount_total), 0))::numeric, 4)         as discount_leakage_pct
from gold.fact_order f
join gold.fact_order_detail fod
    on f.source_system = fod.source_system and f.order_id = fod.order_id
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date         d   on f.date_key        = d.date_key
where dest.channel = 'Delivery'
  and date_trunc('month', d.date) = (
      select date_trunc('month', max(d2.date))
      from gold.dim_date d2
      join gold.fact_order f2 on d2.date_key = f2.date_key
  )
group by dest.destination_name
order by discount_total desc
```

## Delivery Leakage — Net Sales vs Discounts (Most Recent Month)

> LS2 orders carry no destination and fall under the UNKNOWN channel, so they are
> excluded here — delivery-channel figures reflect PAR-sourced orders only.

<BarChart
    data={delivery_leakage}
    x=destination_name
    y={["net_sales","discount_total"]}
    title="Net Sales vs Discounts — Delivery Channels"
    yFmt=usd
    sort=false
/>

<DataTable data={delivery_leakage}>
    <Column id=destination_name    title="Delivery Channel"       />
    <Column id=net_sales           title="Net Sales"      fmt=usd />
    <Column id=discount_total      title="Discounts"      fmt=usd />
    <Column id=discount_leakage_pct title="Leakage %"  fmt=pct1 />
</DataTable>

---

```sql drivethu_monthly
-- C1 cutover: fact_order (order count + avg_ticket by channel/month)
select
    lpad(d.year::int::text, 4, '0') || '-' || lpad(d.month::int::text, 2, '0')                                 as year_month,
    round(sum(f.order_net_sales)::numeric, 2)                                    as net_sales,
    sum(f.order_count)                                                           as order_count,
    round((sum(f.order_net_sales) / nullif(sum(f.order_count), 0))::numeric, 2)  as avg_ticket
from gold.fact_order f
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
    lpad(d.year::int::text, 4, '0') || '-' || lpad(d.month::int::text, 2, '0')                                                    as year_month,
    sum(case when dest.destination_key = 0 then f.order_count else 0 end)                           as unknown_orders,
    sum(f.order_count)                                                                               as total_orders,
    round(
        sum(case when dest.destination_key = 0 then f.order_count else 0 end)::numeric
        / nullif(sum(f.order_count), 0), 4
    )                                                                                                as unknown_pct
from gold.fact_order f
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date         d   on f.date_key        = d.date_key
group by d.year, d.month
order by d.year, d.month
```

## Data Quality: Unknown Destination Monitor

<DataTable data={unknown_destination_trend} title="Unknown destination (key=0) over time" />
