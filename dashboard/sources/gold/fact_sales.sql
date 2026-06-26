-- PARTIAL DEPRECATION (C1+C2 epic, 2026-06-25):
--   order_count superseded by gold.fact_order (C1); "Items Sold" by gold.fact_sale_item.qty (C2).
--   STILL the source for discount_total / tax_amount / tip_amount / net_sales, which the
--   new facts do not carry. Do NOT delete. (Legacy pages forecast/performance/products still
--   read order_count from here until M8 cleanup removes them.)
select * from gold.fact_sales
