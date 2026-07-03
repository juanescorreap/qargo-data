---
title: Items Analysis
---

```sql store_list
select 'All Stores' as store_name, 0 as sort_order
union all
select store_name, 1 as sort_order from gold.dim_store
order by sort_order, store_name
```

```sql size_options
select unnest(array['All','12oz','16oz','20oz','24oz','32oz','Food']) as size_name,
       unnest(array[0,1,2,3,4,5,6]) as sort_order
order by sort_order
```

<Dropdown
    name="store"
    data={store_list}
    value="store_name"
    label="store_name"
    title="Store"
    defaultValue="All Stores"
/>

```sql date_span
-- Bounds for the DateRange picker. Without data/dates the input never initializes,
-- so ${inputs.date_range.start/end} stay undefined and every query on the page errors
-- (blank page). Feed it the min/max sale date so the range defaults to the data span.
select min(d.date) as sale_date
from gold.fact_sale_item f join gold.dim_date d on f.date_key = d.date_key
union all
select max(d.date)
from gold.fact_sale_item f join gold.dim_date d on f.date_key = d.date_key
```

<DateRange
    name="date_range"
    data={date_span}
    dates=sale_date
    title="Date Range"
/>

<Dropdown
    name="size_filter"
    data={size_options}
    value="size_name"
    label="size_name"
    title="Size"
    defaultValue="All"
/>

---

```sql overall_performance
-- C2 cutover: Items Sold = sum(qty) (net of returns) from fact_sale_item
select
    s.store_name,
    round(sum(f.item_net_sales)::numeric, 2) as net_sales,
    sum(f.qty)                               as items_sold
from gold.fact_sale_item f
join gold.dim_date  d on f.date_key  = d.date_key
join gold.dim_store s on f.store_key = s.store_key
where d.date between '${inputs.date_range.start}'::date and '${inputs.date_range.end}'::date
  and (
      '${inputs.store}' = 'All Stores'
      or '${inputs.store}' = ''
      or s.store_name = '${inputs.store}'
  )
group by s.store_name
order by net_sales desc
```

## Overall Performance

<DataTable data={overall_performance} search=true rows=20>
    <Column id=store_name title="Store"               />
    <Column id=net_sales  title="Net Sales"   fmt=usd />
    <Column id=items_sold title="Items Sold"          />
</DataTable>

---

```sql size_breakdown
with filtered as (
    select
        p.product_canonical_name,
        p.revenue_center_name,
        p.product_name,
        sum(f.item_net_sales) as net_sales,
        sum(f.qty)            as items_sold
    from gold.fact_sale_item f
    join gold.dim_date    d on f.date_key    = d.date_key
    join gold.dim_store   s on f.store_key   = s.store_key
    join gold.dim_product p on f.product_key = p.product_key
    where d.date between '${inputs.date_range.start}'::date and '${inputs.date_range.end}'::date
      and p.product_name <> 'UNKNOWN'
      and (
          '${inputs.store}' = 'All Stores'
          or '${inputs.store}' = ''
          or s.store_name = '${inputs.store}'
      )
      and (
          '${inputs.size_filter}' = 'All'
          or ('${inputs.size_filter}' = '12oz' and (p.product_name like '12 OZ %' or p.product_name like '12OZ %'))
          or ('${inputs.size_filter}' = '16oz' and (p.product_name like '16 OZ %' or p.product_name like '16OZ %'))
          or ('${inputs.size_filter}' = '20oz' and (p.product_name like '20 OZ %' or p.product_name like '20OZ %'))
          or ('${inputs.size_filter}' = '24oz' and (p.product_name like '24 OZ %' or p.product_name like '24OZ %'))
          or ('${inputs.size_filter}' = '32oz' and (p.product_name like '32 OZ %' or p.product_name like '32OZ %'))
          or ('${inputs.size_filter}' = 'Food' and p.revenue_center_name = 'Food')
      )
    group by p.product_canonical_name, p.revenue_center_name, p.product_name
),
totals as (
    select sum(net_sales) as total_net_sales from filtered
)
select
    f.product_canonical_name,
    f.revenue_center_name,
    round(f.net_sales::numeric, 2)                                                   as net_sales,
    f.items_sold,
    round((f.net_sales / nullif(t.total_net_sales, 0))::numeric, 4)                  as pct_of_sales
from filtered f
cross join totals t
where f.net_sales > 0
order by f.net_sales desc
limit 200
```

## Size Breakdown

<DataTable data={size_breakdown} search=true rows=25>
    <Column id=product_canonical_name title="Product"          />
    <Column id=revenue_center_name    title="Category"         />
    <Column id=net_sales              title="Net Sales" fmt=usd />
    <Column id=items_sold             title="Items Sold"        />
    <Column id=pct_of_sales           title="% of Sales" fmt=pct1 />
</DataTable>

<BarChart
    data={size_breakdown}
    x=product_canonical_name
    y=net_sales
    title="Net Sales by Product"
    yFmt=usd
    swapXY=true
    sort=true
/>
