---
title: Revenue Centers & Menu
---

```sql attachment_rate_kpi
select
    sum(beverage_orders)  as beverage_orders,
    sum(paired_orders)    as paired_orders,
    round(
        sum(paired_orders)::numeric / nullif(sum(beverage_orders), 0) * 100, 1
    )                     as attachment_rate_pct
from attachment_rate_monthly
```

```sql attachment_rate_trend
select
    year_month,
    beverage_orders,
    paired_orders,
    attachment_rate_pct
from attachment_rate_monthly
order by year_month
```

## Food Attachment Rate

<BigValue
    data={attachment_rate_kpi}
    value=attachment_rate_pct
    title="Food Attach Rate (All Time)"
    fmt=num1
/>
<BigValue
    data={attachment_rate_kpi}
    value=beverage_orders
    title="Total Beverage Orders"
/>
<BigValue
    data={attachment_rate_kpi}
    value=paired_orders
    title="Orders with Food + Beverage"
/>

<LineChart
    data={attachment_rate_trend}
    x=year_month
    y=attachment_rate_pct
    title="Food Attachment Rate % — Monthly Trend"
/>

---

```sql retail_evolution
select
    d.year || '-' || lpad(d.month::text, 2, '0')                   as year_month,
    round(sum(f.net_sales)::numeric, 2)                             as net_sales,
    sum(f.order_count)                                              as order_count
from gold.fact_sales f
join gold.dim_date    d on f.date_key    = d.date_key
join gold.dim_product p on f.product_key = p.product_key
where p.revenue_center_name = 'Retail'
  and d.date >= '2024-07-01'::date
group by d.year, d.month
order by d.year, d.month
```

```sql product_mix_by_category
select
    d.year || '-' || lpad(d.month::text, 2, '0')                   as year_month,
    p.revenue_center_name,
    round(sum(f.net_sales)::numeric, 2)                             as net_sales
from gold.fact_sales f
join gold.dim_date    d on f.date_key    = d.date_key
join gold.dim_product p on f.product_key = p.product_key
where d.date >= '2024-07-01'::date
  and p.revenue_center_name in ('Beverage','Food','Retail','Other')
group by d.year, d.month, p.revenue_center_name
order by d.year, d.month
```

## Product Mix Evolution — Since July 2024

<AreaChart
    data={product_mix_by_category}
    x=year_month
    y=net_sales
    series=revenue_center_name
    title="Net Sales by Category (Stacked) — Since Jul 2024"
    yFmt=usd
/>

<LineChart
    data={retail_evolution}
    x=year_month
    y=net_sales
    title="Retail Category Net Sales — Since Jul 2024"
    yFmt=usd
/>

---

```sql top_products_by_revenue
select
    p.product_canonical_name,
    p.revenue_center_name,
    round(sum(f.net_sales)::numeric, 2)   as net_sales,
    sum(f.order_count)                    as order_count,
    round(avg(f.avg_ticket)::numeric, 2)  as avg_ticket
from gold.fact_sales f
join gold.dim_product p on f.product_key = p.product_key
join gold.dim_date    d on f.date_key    = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sales f2 on d2.date_key = f2.date_key
)
  and p.product_name <> 'UNKNOWN'
group by p.product_canonical_name, p.revenue_center_name
order by net_sales desc
limit 30
```

## Top Products by Revenue — Most Recent Month

<DataTable data={top_products_by_revenue} search=true rows=25>
    <Column id=product_canonical_name title="Product"               />
    <Column id=revenue_center_name    title="Category"              />
    <Column id=net_sales              title="Net Sales"    fmt=usd  />
    <Column id=order_count            title="Orders"                />
    <Column id=avg_ticket             title="Avg Ticket"  fmt=usd  />
</DataTable>

---

## Estimated Waste Analysis

> **Coming Soon** — This section will map Net Sales against theoretical inventory depletion once the inventory management system is integrated.
>
> Planned metrics:
> - Theoretical units sold by SKU
> - Variance between expected and actual inventory counts
> - Waste cost by product category

```sql waste_placeholder
select
    p.revenue_center_name                           as category,
    round(sum(f.net_sales)::numeric, 2)             as net_sales,
    sum(f.order_count)                              as orders_processed
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

<DataTable data={waste_placeholder} title="Category Volume (Inventory Integration Hook)">
    <Column id=category         title="Category"           />
    <Column id=net_sales        title="Net Sales" fmt=usd  />
    <Column id=orders_processed title="Orders Processed"   />
</DataTable>
