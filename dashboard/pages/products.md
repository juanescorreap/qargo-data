---
title: Products & Channels
---

```sql category_mix_this_month
select
    p.revenue_center_name,
    round(sum(f.net_sales)::numeric, 2)                                                               as net_sales,
    round(sum(f.net_sales) / sum(sum(f.net_sales)) over () * 100, 1)                                  as pct_of_total,
    sum(f.order_count)                                                                                 as order_count,
    round(avg(f.avg_ticket)::numeric, 2)                                                              as avg_ticket,
    round(sum(f.discount_total)::numeric, 2)                                                          as discount_total,
    round((sum(f.discount_total) / nullif(sum(f.net_sales + f.discount_total), 0) * 100)::numeric, 2) as discount_pct
from gold.fact_sales f
join gold.dim_product p on f.product_key = p.product_key
join gold.dim_date    d on f.date_key    = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
group by p.revenue_center_name
order by net_sales desc
```

```sql category_by_month
select
    d.year || '-' || lpad(d.month::text, 2, '0') as year_month,
    p.revenue_center_name,
    round(sum(f.net_sales)::numeric, 2)           as net_sales
from gold.fact_sales f
join gold.dim_product p on f.product_key = p.product_key
join gold.dim_date    d on f.date_key    = d.date_key
group by d.year, d.month, p.revenue_center_name
order by d.year, d.month
```

```sql category_discount_analysis
select
    p.revenue_center_name,
    round(sum(f.net_sales)::numeric, 2)                                                               as net_sales,
    round((sum(f.net_sales) + sum(f.discount_total))::numeric, 2)                                     as gross_sales,
    round(sum(f.discount_total)::numeric, 2)                                                          as discount_total,
    round((sum(f.discount_total) / nullif(sum(f.net_sales + f.discount_total), 0) * 100)::numeric, 2) as discount_pct
from gold.fact_sales f
join gold.dim_product p on f.product_key = p.product_key
join gold.dim_date    d on f.date_key    = d.date_key
where d.year = extract(year from current_date)::int
group by p.revenue_center_name
order by discount_pct desc
```

```sql channel_comparison
select
    dest.channel,
    round(sum(f.net_sales)::numeric, 2)           as net_sales,
    sum(f.order_count)                            as order_count,
    round(avg(f.avg_ticket)::numeric, 2)          as avg_ticket,
    round((sum(f.net_sales) / sum(sum(f.net_sales)) over () * 100)::numeric, 1) as pct_of_total
from gold.fact_sales f
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date         d   on f.date_key        = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
group by dest.channel
order by net_sales desc
```

```sql channel_avg_ticket
select
    dest.channel,
    round(avg(f.avg_ticket)::numeric, 2) as avg_ticket,
    sum(f.order_count)                   as order_count
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
order by avg_ticket desc
```

```sql unknown_destination_monitor
select
    d.year || '-' || lpad(d.month::text, 2, '0') as year_month,
    sum(case when dest.destination_key = 0 then f.order_count else 0 end) as unknown_orders,
    sum(f.order_count)                                                     as total_orders,
    round(
        sum(case when dest.destination_key = 0 then f.order_count else 0 end)::numeric
        / nullif(sum(f.order_count), 0) * 100, 1
    ) as unknown_pct
from gold.fact_sales f
join gold.dim_destination dest on f.destination_key = dest.destination_key
join gold.dim_date         d   on f.date_key        = d.date_key
group by d.year, d.month
order by d.year, d.month
```

## Sales Mix by Category, This Month

<BarChart
    data={category_mix_this_month}
    x=revenue_center_name
    y=net_sales
    title="Net Sales by Category"
/>

<DataTable data={category_mix_this_month} />

## Category Sales by Month

<BarChart
    data={category_by_month}
    x=year_month
    y=net_sales
    series=revenue_center_name
    title="Monthly Sales by Category"
/>

## Discount Impact by Category, YTD

<BarChart
    data={category_discount_analysis}
    x=revenue_center_name
    y=discount_pct
    title="Discount % by Category (lower is better)"
/>

<DataTable data={category_discount_analysis} />

## Omnichannel, This Month

<BarChart
    data={channel_comparison}
    x=channel
    y=net_sales
    title="Net Sales by Channel"
/>

<DataTable data={channel_comparison} />

## Avg Ticket by Channel, This Month

<BarChart
    data={channel_avg_ticket}
    x=channel
    y=avg_ticket
    title="Avg Ticket by Channel"
    sort=true
/>

## Data Quality: Unknown Destination Monitor

<DataTable
    data={unknown_destination_monitor}
    title="Unknown destination_key = 0 over time"
/>
