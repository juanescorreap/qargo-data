-- Referential integrity: every order in fact_sale_item must exist in fact_order.
--
-- Both facts derive order identity from the same order_ref. An item line with no
-- parent order means the two models have drifted apart (different filters, dim
-- coverage, or order-key logic). Returns orphan (source_system, order_id) pairs;
-- dbt test passes only when zero rows are returned.

select
    i.source_system,
    i.order_id
from {{ ref('fact_sale_item') }} i
left join {{ ref('fact_order') }} o
    on i.source_system = o.source_system
   and i.order_id      = o.order_id
where o.order_id is null
group by i.source_system, i.order_id
