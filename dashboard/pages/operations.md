---
title: Labor & Operations
---

<!--
This page (Up-selling Leaderboard, Tip Performance, Shift Productivity, Discount
Audit) is built entirely on per-employee grain from gold.fact_sales_by_employee,
which was dropped in the C5 space reduction. Every tile also needs tip_amount /
discount_total, which lived only in fact_sales/fact_sales_by_employee.

Restore the whole page via a fact_by_employee / fact_order_detail model (next epic)
carrying employee_key + tip_amount + discount_total. All original queries were
removed here to unblock the Evidence build.
-->

## Labor & Operations

_Esta página requiere `fact_by_employee` (próxima épica). Temporalmente deshabilitada._
