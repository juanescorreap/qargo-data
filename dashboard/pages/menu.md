---
title: Revenue Centers & Menu
---

```sql attachment_rate_kpi
select
    sum(beverage_orders)  as beverage_orders,
    sum(paired_orders)    as paired_orders,
    round(
        sum(paired_orders)::numeric / nullif(sum(beverage_orders), 0), 4
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

> **Food Attach Rate** = % of beverage orders that also include at least one food item. Calculated as: Orders with Food + Beverage / Total Beverage Orders.

<BigValue
    data={attachment_rate_kpi}
    value=attachment_rate_pct
    title="Food Attach Rate (All Time)"
    fmt=pct1
/>
<BigValue
    data={attachment_rate_kpi}
    value=beverage_orders
    title="Total Beverage Orders"
    fmt=num0
/>
<BigValue
    data={attachment_rate_kpi}
    value=paired_orders
    title="Orders with Food + Beverage"
    fmt=num0
/>

<LineChart
    data={attachment_rate_trend}
    x=year_month
    y=attachment_rate_pct
    yFmt=pct1
    title="Food Attachment Rate % — Monthly Trend"
/>

---

```sql retail_evolution
-- Migrated off deprecated fact_sales to fact_sale_item (product-grain net sales).
select
    lpad(d.year::int::text, 4, '0') || '-' || lpad(d.month::int::text, 2, '0')   as year_month,
    round(sum(f.item_net_sales)::numeric, 2)                        as net_sales,
    sum(f.qty)                                                      as items_sold
from gold.fact_sale_item f
join gold.dim_date    d on f.date_key    = d.date_key
join gold.dim_product p on f.product_key = p.product_key
where p.revenue_center_name = 'Retail'
  and d.date >= '2024-07-01'::date
group by d.year, d.month
order by d.year, d.month
```

```sql product_mix_by_category
-- Migrated off deprecated fact_sales to fact_sale_item (product-grain net sales).
select
    lpad(d.year::int::text, 4, '0') || '-' || lpad(d.month::int::text, 2, '0')   as year_month,
    p.revenue_center_name,
    round(sum(f.item_net_sales)::numeric, 2)                        as net_sales
from gold.fact_sale_item f
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
-- C2 cutover: product grain -> fact_sale_item. "Orders per product" is not meaningful
-- (an order spans products), so replaced by Items Sold (qty) and Avg Unit Price.
select
    p.product_canonical_name,
    p.revenue_center_name,
    round(sum(f.item_net_sales)::numeric, 2)                                    as net_sales,
    sum(f.qty)                                                                  as items_sold,
    round((sum(f.item_net_sales) / nullif(sum(f.qty), 0))::numeric, 2)          as avg_unit_price
from gold.fact_sale_item f
join gold.dim_product p on f.product_key = p.product_key
join gold.dim_date    d on f.date_key    = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sale_item f2 on d2.date_key = f2.date_key
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
    <Column id=items_sold             title="Items Sold"            />
    <Column id=avg_unit_price         title="Avg Unit Price" fmt=usd />
</DataTable>

---

## Estimated Waste Analysis

> **Coming Soon** — This section will map Net Sales against theoretical inventory depletion once the inventory management system is integrated.
>
> Planned metrics:
> - Theoretical units sold by SKU
> - Variance between expected and actual inventory counts
> - Waste cost by product category

```sql category_volume
-- C2 cutover: product/category grain -> fact_sale_item (items sold, net of returns).
-- Most-recent-month category volume: qty, net sales, and each category's share of net
-- sales. Serves as the inventory-integration hook until the real waste system lands.
select
    p.revenue_center_name                                                             as revenue_center,
    sum(f.qty)                                                                         as total_qty,
    round(sum(f.item_net_sales)::numeric, 2)                                           as net_sales,
    round((sum(f.item_net_sales) / sum(sum(f.item_net_sales)) over ())::numeric, 4) as pct_of_total
from gold.fact_sale_item f
join gold.dim_product p on f.product_key = p.product_key
join gold.dim_date    d on f.date_key    = d.date_key
where date_trunc('month', d.date) = (
    select date_trunc('month', max(d2.date))
    from gold.dim_date d2
    join gold.fact_sale_item f2 on d2.date_key = f2.date_key
)
group by p.revenue_center_name
order by net_sales desc
```

<DataTable data={category_volume} title="Category Volume — Most Recent Month (Inventory Integration Hook)">
    <Column id=revenue_center title="Category"           />
    <Column id=total_qty      title="Total Qty"          />
    <Column id=net_sales      title="Net Sales" fmt=usd  />
    <Column id=pct_of_total   title="% of Total" fmt=pct1 />
</DataTable>
