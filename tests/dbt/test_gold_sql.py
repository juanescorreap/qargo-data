"""
Unit tests for the gold-layer transformation logic
(dim_date, dim_store, dim_product, fact_sales) using DuckDB.

These tests verify:
- dim_date: date range, key format, weekend detection, calendar attributes
- dim_store: royalty-rate assignment per store type
- dim_product: completeness of the product dimension
- fact_sales: aggregation maths (net_sales, order_count, avg_ticket)
"""

from datetime import date

import duckdb
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(sql: str) -> list[tuple]:
    con = duckdb.connect()
    return con.execute(sql).fetchall()


def _scalar(sql: str):
    return _run(sql)[0][0]


# ---------------------------------------------------------------------------
# dim_date
# ---------------------------------------------------------------------------

# We reproduce the core dim_date logic using DuckDB's generate_series.
# DuckDB does not have to_char(), so we use strftime() instead — the logic
# under test is the same; we're validating the calendar arithmetic.

DIM_DATE_SQL = """
with dates as (
    -- DuckDB 1.5: generate_series returns TIMESTAMP[]; unnest + cast to DATE
    select unnest(generate_series(
        DATE '2024-07-01',
        (current_date + interval '3 years')::date,
        interval '1 day'
    ))::date as date
)
select
    cast(strftime(date, '%Y%m%d') as integer)  as date_key,
    date,
    extract(isodow from date)::integer         as day_of_week,
    strftime(date, '%A')                       as day_name,
    extract(week    from date)::integer        as week_number,
    extract(month   from date)::integer        as month,
    strftime(date, '%B')                       as month_name,
    extract(quarter from date)::integer        as quarter,
    extract(year    from date)::integer        as year,
    extract(isodow  from date) in (6, 7)       as is_weekend
from dates
"""


@pytest.fixture(scope="module")
def dim_date():
    import pandas as pd
    con = duckdb.connect()
    df = con.execute(DIM_DATE_SQL).df()
    # DuckDB may return Timestamps; normalize to Python date for clean comparisons
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


class TestDimDateRange:
    def test_starts_from_2024_07_01(self, dim_date):
        assert dim_date["date"].min() == date(2024, 7, 1)

    def test_extends_at_least_3_years_from_today(self, dim_date):
        from datetime import date as dt, timedelta
        three_years_from_now = dt.today() + timedelta(days=3 * 365)
        assert dim_date["date"].max() >= three_years_from_now

    def test_no_gaps_in_date_sequence(self, dim_date):
        dates = sorted(dim_date["date"].tolist())
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i - 1]).days
            assert gap == 1, f"Gap of {gap} days found between {dates[i-1]} and {dates[i]}"


class TestDimDateKey:
    def test_date_key_is_yyyymmdd_integer(self, dim_date):
        row = dim_date[dim_date["date"] == date(2025, 1, 15)].iloc[0]
        assert int(row["date_key"]) == 20250115

    def test_date_key_for_jan_1_2025(self, dim_date):
        row = dim_date[dim_date["date"] == date(2025, 1, 1)].iloc[0]
        assert int(row["date_key"]) == 20250101

    def test_date_keys_are_unique(self, dim_date):
        assert dim_date["date_key"].nunique() == len(dim_date)


class TestDimDateWeekend:
    def test_saturday_is_weekend(self, dim_date):
        # 2025-01-04 is Saturday
        row = dim_date[dim_date["date"] == date(2025, 1, 4)].iloc[0]
        assert row["is_weekend"] is True or row["is_weekend"] == 1

    def test_sunday_is_weekend(self, dim_date):
        # 2025-01-05 is Sunday
        row = dim_date[dim_date["date"] == date(2025, 1, 5)].iloc[0]
        assert row["is_weekend"] is True or row["is_weekend"] == 1

    def test_monday_is_not_weekend(self, dim_date):
        # 2025-01-06 is Monday
        row = dim_date[dim_date["date"] == date(2025, 1, 6)].iloc[0]
        assert row["is_weekend"] is False or row["is_weekend"] == 0

    def test_friday_is_not_weekend(self, dim_date):
        # 2025-01-03 is Friday
        row = dim_date[dim_date["date"] == date(2025, 1, 3)].iloc[0]
        assert row["is_weekend"] is False or row["is_weekend"] == 0

    def test_isodow_monday_is_1(self, dim_date):
        row = dim_date[dim_date["date"] == date(2025, 1, 6)].iloc[0]
        assert int(row["day_of_week"]) == 1

    def test_isodow_saturday_is_6(self, dim_date):
        row = dim_date[dim_date["date"] == date(2025, 1, 4)].iloc[0]
        assert int(row["day_of_week"]) == 6

    def test_isodow_sunday_is_7(self, dim_date):
        row = dim_date[dim_date["date"] == date(2025, 1, 5)].iloc[0]
        assert int(row["day_of_week"]) == 7


class TestDimDateCalendar:
    def test_month_number_correct(self, dim_date):
        row = dim_date[dim_date["date"] == date(2025, 3, 15)].iloc[0]
        assert int(row["month"]) == 3

    def test_quarter_q1(self, dim_date):
        row = dim_date[dim_date["date"] == date(2025, 2, 1)].iloc[0]
        assert int(row["quarter"]) == 1

    def test_quarter_q4(self, dim_date):
        row = dim_date[dim_date["date"] == date(2025, 11, 1)].iloc[0]
        assert int(row["quarter"]) == 4

    def test_year_correct(self, dim_date):
        row = dim_date[dim_date["date"] == date(2025, 6, 15)].iloc[0]
        assert int(row["year"]) == 2025


# ---------------------------------------------------------------------------
# dim_store
# ---------------------------------------------------------------------------

DIM_STORE_SQL = """
with stores as (
    select unnest([
        'MEIJER GRAND RAPIDS',
        'MEIJER ANN ARBOR',
        'LAS VEGAS',
        'BERKELEY',
        'DOWNTOWN',
        'EDINBURG'
    ]) as store_name
)
select
    store_name,
    case
        when store_name like 'MEIJER%' then 0.04
        when store_name = 'LAS VEGAS'  then 0.08
        else                                0.07
    end::numeric(5,2) as royalty_rate,
    true as is_active
from stores
"""


@pytest.fixture(scope="module")
def dim_store():
    con = duckdb.connect()
    return con.execute(DIM_STORE_SQL).df()


class TestDimStoreRoyaltyRates:
    def _rate(self, dim_store, store_name: str) -> float:
        row = dim_store[dim_store["store_name"] == store_name]
        assert len(row) == 1, f"Store '{store_name}' not found"
        return float(row.iloc[0]["royalty_rate"])

    def test_meijer_grand_rapids_is_4_percent(self, dim_store):
        assert self._rate(dim_store, "MEIJER GRAND RAPIDS") == pytest.approx(0.04)

    def test_meijer_ann_arbor_is_4_percent(self, dim_store):
        assert self._rate(dim_store, "MEIJER ANN ARBOR") == pytest.approx(0.04)

    def test_las_vegas_is_8_percent(self, dim_store):
        assert self._rate(dim_store, "LAS VEGAS") == pytest.approx(0.08)

    def test_other_stores_are_7_percent(self, dim_store):
        for store in ["BERKELEY", "DOWNTOWN", "EDINBURG"]:
            assert self._rate(dim_store, store) == pytest.approx(0.07), store

    def test_all_stores_active(self, dim_store):
        assert (dim_store["is_active"] == True).all()


# ---------------------------------------------------------------------------
# dim_product  (derived from source data, not hardcoded)
# ---------------------------------------------------------------------------
# dim_product now has one row per unique product_name from raw_par2 / raw_ls2,
# plus an UNKNOWN fallback row (key = 0).  We test the structural invariants
# using synthetic source-data rows that exercise both PAR and LS2 paths.

DIM_PRODUCT_SQL = """
with par_products as (
    select * from (values
        ('16 OZ ICED LATTE',    regexp_replace('16 OZ ICED LATTE',    '^[0-9]+\\s*OZ\\s+', ''), 'Beverage'),
        ('20 OZ ICED LATTE',    regexp_replace('20 OZ ICED LATTE',    '^[0-9]+\\s*OZ\\s+', ''), 'Beverage'),
        ('QARGO CLASSIC',       regexp_replace('QARGO CLASSIC',       '^[0-9]+\\s*OZ\\s+', ''), 'Food'),
        ('4 OZ ESPRESSO',       regexp_replace('4 OZ ESPRESSO',       '^[0-9]+\\s*OZ\\s+', ''), 'Beverage'),
        ('ALMOND CROISSANT',    regexp_replace('ALMOND CROISSANT',    '^[0-9]+\\s*OZ\\s+', ''), 'Food')
    ) t(product_name, product_canonical_name, revenue_center_name)
),
ls2_products as (
    select * from (values
        ('ICED LATTE (16 OZ) M', regexp_replace('ICED LATTE (16 OZ) M','\\s*\\(\\s*[0-9]+\\s*OZ\\s*\\)\\s*[A-Za-z]{0,3}\\s*$',''), 'Beverage'),
        ('QARGO CLASSIC',        regexp_replace('QARGO CLASSIC',       '\\s*\\(\\s*[0-9]+\\s*OZ\\s*\\)\\s*[A-Za-z]{0,3}\\s*$',''), 'Food'),
        ('ALMOND CROISSANT',     regexp_replace('ALMOND CROISSANT',    '\\s*\\(\\s*[0-9]+\\s*OZ\\s*\\)\\s*[A-Za-z]{0,3}\\s*$',''), 'Food'),
        ('ESPRESSO (4OZ)',        regexp_replace('ESPRESSO (4OZ)',      '\\s*\\(\\s*[0-9]+\\s*OZ\\s*\\)\\s*[A-Za-z]{0,3}\\s*$',''), 'Beverage')
    ) t(product_name, product_canonical_name, revenue_center_name)
),
combined as (
    select product_name, product_canonical_name, revenue_center_name from par_products
    union
    select product_name, product_canonical_name, revenue_center_name from ls2_products
),
with_key as (
    select
        abs(hash(product_name)) as product_key,
        product_name,
        product_canonical_name,
        revenue_center_name
    from combined
    where product_name is not null and trim(product_name) <> ''
)
select * from with_key
union all
select 0, 'UNKNOWN', 'UNKNOWN', 'Other'
"""


@pytest.fixture(scope="module")
def dim_product():
    con = duckdb.connect()
    return con.execute(DIM_PRODUCT_SQL).df()


class TestDimProduct:
    def test_product_keys_unique(self, dim_product):
        assert dim_product["product_key"].nunique() == len(dim_product)

    def test_product_names_unique(self, dim_product):
        assert dim_product["product_name"].nunique() == len(dim_product)

    def test_no_null_product_name(self, dim_product):
        assert dim_product["product_name"].notna().all()

    def test_no_null_product_canonical_name(self, dim_product):
        assert dim_product["product_canonical_name"].notna().all()

    def test_revenue_center_only_valid_values(self, dim_product):
        valid = {"Beverage", "Food", "Retail", "Other"}
        actual = set(dim_product["revenue_center_name"].tolist())
        assert actual.issubset(valid)

    def test_all_revenue_centers_represented(self, dim_product):
        # Beverage, Food, Other (from UNKNOWN row) must all be present
        actual = set(dim_product["revenue_center_name"].tolist())
        assert {"Beverage", "Food", "Other"}.issubset(actual)

    def test_unknown_row_present_with_key_zero(self, dim_product):
        unknown = dim_product[dim_product["product_name"] == "UNKNOWN"]
        assert len(unknown) == 1
        assert int(unknown.iloc[0]["product_key"]) == 0

    def test_cross_system_deduplication(self, dim_product):
        # QARGO CLASSIC and ALMOND CROISSANT exist in both systems → one row each
        for name in ["QARGO CLASSIC", "ALMOND CROISSANT"]:
            rows = dim_product[dim_product["product_name"] == name]
            assert len(rows) == 1, f"Duplicate found for {name}"

    def test_par_size_variants_have_same_canonical(self, dim_product):
        r16 = dim_product[dim_product["product_name"] == "16 OZ ICED LATTE"].iloc[0]
        r20 = dim_product[dim_product["product_name"] == "20 OZ ICED LATTE"].iloc[0]
        assert r16["product_canonical_name"] == r20["product_canonical_name"] == "ICED LATTE"

    def test_ls2_size_variant_canonical_matches_par_base(self, dim_product):
        ls2_row = dim_product[dim_product["product_name"] == "ICED LATTE (16 OZ) M"].iloc[0]
        assert ls2_row["product_canonical_name"] == "ICED LATTE"

    def test_espresso_canonical_stripped(self, dim_product):
        row = dim_product[dim_product["product_name"] == "4 OZ ESPRESSO"].iloc[0]
        assert row["product_canonical_name"] == "ESPRESSO"

    def test_food_item_canonical_equals_name(self, dim_product):
        row = dim_product[dim_product["product_name"] == "QARGO CLASSIC"].iloc[0]
        assert row["product_canonical_name"] == "QARGO CLASSIC"


# ---------------------------------------------------------------------------
# fact_sales — aggregation logic
# ---------------------------------------------------------------------------


FACT_SALES_LOGIC_SQL = """
-- Minimal stub of the fact_sales aggregation logic (product_name grain)
with orders as (
    select * from (values
        -- sale_date, store_name, net_sales, order_id, tip, destination, tax, discount, product_name
        (DATE '2025-01-01', 'BERKELEY', 10.00, 'A001', 0.0, 'DINE IN', 0.80, 0.00, '16 OZ ICED LATTE'),
        (DATE '2025-01-01', 'BERKELEY', 15.00, 'A002', 1.0, 'DINE IN', 1.20, 0.50, '16 OZ ICED LATTE'),
        (DATE '2025-01-01', 'BERKELEY',  5.00, 'A001', 0.0, 'DINE IN', 0.40, 0.00, '16 OZ ICED LATTE'),
        (DATE '2025-01-02', 'BERKELEY',  8.00, 'A003', 0.5, 'TO GO',   0.64, 0.00, 'QARGO CLASSIC')
    ) t(sale_date, store_name, net_sales, order_id, tip_amount,
        destination, tax_amount, discount_total, product_name)
),
dim_date as (
    select
        cast(strftime(date, '%Y%m%d') as integer) as date_key,
        date
    from (values (DATE '2025-01-01'), (DATE '2025-01-02')) t(date)
),
dim_store as (
    select 9001 as store_key, 'BERKELEY' as store_name
),
dim_product as (
    select 1 as product_key, '16 OZ ICED LATTE' as product_name, 'ICED LATTE' as product_canonical_name, 'Beverage' as revenue_center_name
    union all select 2, 'QARGO CLASSIC', 'QARGO CLASSIC', 'Food'
    union all select 0, 'UNKNOWN',       'UNKNOWN',        'Other'
),
dim_destination as (
    select 1001::bigint as destination_key, 'DINE IN' as destination_name
    union all select 1002::bigint, 'TO GO'
    union all select 0::bigint,   'UNKNOWN'
),
joined as (
    select
        d.date_key,
        s.store_key,
        coalesce(dest.destination_key, 0) as destination_key,
        coalesce(p.product_key, 0)        as product_key,
        o.net_sales,
        o.order_id,
        o.tip_amount,
        o.tax_amount,
        o.discount_total
    from orders o
    inner join dim_date        d    on o.sale_date                           = d.date
    inner join dim_store       s    on o.store_name                          = s.store_name
    left  join dim_product     p    on upper(trim(o.product_name))           = p.product_name
    left  join dim_destination dest on coalesce(o.destination, 'UNKNOWN')   = dest.destination_name
)
select
    date_key,
    store_key,
    product_key,
    destination_key,
    sum(net_sales)                                                              as net_sales,
    count(distinct order_id)                                                    as order_count,
    sum(tip_amount)                                                             as tip_amount,
    sum(tax_amount)                                                             as tax_amount,
    sum(discount_total)                                                         as discount_total,
    round((sum(net_sales) / nullif(count(distinct order_id), 0))::numeric, 2)  as avg_ticket
from joined
group by date_key, store_key, product_key, destination_key
order by date_key, product_key
"""


@pytest.fixture(scope="module")
def fact_sales():
    con = duckdb.connect()
    return con.execute(FACT_SALES_LOGIC_SQL).df()


class TestFactSalesAggregation:
    def test_two_rows_output(self, fact_sales):
        # Jan 1 16 OZ ICED LATTE + Jan 2 QARGO CLASSIC
        assert len(fact_sales) == 2

    def test_net_sales_summed_correctly(self, fact_sales):
        # Jan 1: 10 + 15 + 5 = 30 (all three rows are 16 OZ ICED LATTE)
        bev_row = fact_sales[fact_sales["product_key"] == 1].iloc[0]
        assert float(bev_row["net_sales"]) == pytest.approx(30.0)

    def test_order_count_is_distinct_orders(self, fact_sales):
        # Jan 1: A001 (x2) + A002 → 2 distinct orders
        bev_row = fact_sales[fact_sales["product_key"] == 1].iloc[0]
        assert int(bev_row["order_count"]) == 2

    def test_avg_ticket_calculated(self, fact_sales):
        # Jan 1: 30 / 2 = 15.00
        bev_row = fact_sales[fact_sales["product_key"] == 1].iloc[0]
        assert float(bev_row["avg_ticket"]) == pytest.approx(15.0)

    def test_food_row_correct(self, fact_sales):
        food_row = fact_sales[fact_sales["product_key"] == 2].iloc[0]
        assert float(food_row["net_sales"]) == pytest.approx(8.0)
        assert int(food_row["order_count"]) == 1
        assert float(food_row["avg_ticket"]) == pytest.approx(8.0)

    def test_tip_amount_summed(self, fact_sales):
        bev_row = fact_sales[fact_sales["product_key"] == 1].iloc[0]
        assert float(bev_row["tip_amount"]) == pytest.approx(1.0)

    def test_avg_ticket_null_when_zero_orders(self):
        sql = """
        select round((0.0 / nullif(0, 0))::numeric, 2) as avg_ticket
        """
        result = _scalar(sql)
        assert result is None


class TestFactSalesJoinBehavior:
    def test_unmatched_store_excluded_by_inner_join(self):
        sql = """
        with orders as (
            select DATE '2025-01-01' as sale_date, 'UNKNOWN_STORE' as store_name,
                   'Beverage' as revenue_center, 10.0 as net_sales,
                   'A001' as order_id, 0.0 as tip_amount
        ),
        dim_date as (select cast(strftime(DATE '2025-01-01', '%Y%m%d') as int) as date_key, DATE '2025-01-01' as date),
        dim_store as (select 1 as store_key, 'BERKELEY' as store_name)
        select count(*) from orders o
        inner join dim_date  d on o.sale_date  = d.date
        inner join dim_store s on o.store_name = s.store_name
        """
        assert _scalar(sql) == 0

    def test_null_product_key_when_product_name_unmatched(self):
        sql = """
        with orders as (
            select 'SOME UNKNOWN ITEM' as product_name, 5.0 as net_sales
        ),
        dim_product as (
            select 1 as product_key, '16 OZ ICED LATTE' as product_name
        )
        select p.product_key
        from orders o
        left join dim_product p on upper(trim(o.product_name)) = p.product_name
        """
        result = _run(sql)
        assert result[0][0] is None

    def test_unique_key_is_date_store_product_destination(self):
        sql = """
        select count(*) = count(distinct (date_key, store_key, product_key, destination_key))
        from ({fact})
        """.format(fact=FACT_SALES_LOGIC_SQL)
        assert _scalar(sql) in (True, 1)

    def test_destination_key_propagated(self):
        sql = """
        select destination_key from ({fact}) where product_key = 1
        """.format(fact=FACT_SALES_LOGIC_SQL)
        assert _run(sql)[0][0] == 1001

    def test_tax_amount_summed(self):
        # Beverage rows: 0.80 + 1.20 + 0.40 = 2.40
        sql = """
        select tax_amount from ({fact}) where product_key = 1
        """.format(fact=FACT_SALES_LOGIC_SQL)
        assert float(_run(sql)[0][0]) == pytest.approx(2.40)

    def test_discount_total_summed(self):
        # Beverage rows: 0.0 + 0.50 + 0.0 = 0.50
        sql = """
        select discount_total from ({fact}) where product_key = 1
        """.format(fact=FACT_SALES_LOGIC_SQL)
        assert float(_run(sql)[0][0]) == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# dim_destination — channel classification
# ---------------------------------------------------------------------------

DESTINATION_CHANNEL_EXPR = """
select
    case
        when dest ilike '%dine%'     then 'In-Store'
        when dest ilike '%drive%'    then 'Drive-Thru'
        when dest ilike '%go%'       then 'Takeout'
        when dest ilike '%delivery%' then 'Delivery'
        when dest ilike '%cater%'    then 'Catering'
        else                              'Other'
    end as channel
from (values (?)) t(dest)
"""


def _channel(dest: str) -> str:
    con = duckdb.connect()
    return con.execute(DESTINATION_CHANNEL_EXPR, [dest]).fetchone()[0]


class TestDimDestinationChannel:
    def test_dine_in_is_instore(self):
        assert _channel("DINE IN") == "In-Store"

    def test_drive_thru_is_drive_thru(self):
        assert _channel("DRIVE THRU") == "Drive-Thru"

    def test_to_go_is_takeout(self):
        assert _channel("TO GO") == "Takeout"

    def test_delivery_is_delivery(self):
        assert _channel("DELIVERY") == "Delivery"

    def test_catering_is_catering(self):
        assert _channel("CATERING") == "Catering"

    def test_unknown_is_other(self):
        assert _channel("KIOSK") == "Other"

    def test_unknown_row_always_present(self):
        sql = """
        select count(*) from (
            select 0::bigint as destination_key, 'UNKNOWN' as destination_name, 'Unknown' as channel
        ) where destination_name = 'UNKNOWN'
        """
        assert _scalar(sql) == 1


# ---------------------------------------------------------------------------
# dim_employee — numeric ID filtering
# ---------------------------------------------------------------------------


class TestDimEmployeeFilter:
    def test_real_name_passes(self):
        sql = "select 'JOHN DOE' !~ '^[0-9]+$'"
        assert _scalar(sql) is True

    def test_numeric_id_excluded(self):
        sql = "select '673508831' !~ '^[0-9]+$'"
        assert _scalar(sql) is False

    def test_short_numeric_excluded(self):
        sql = "select '12345' !~ '^[0-9]+$'"
        assert _scalar(sql) is False

    def test_alphanumeric_name_passes(self):
        sql = "select 'CASHIER1' !~ '^[0-9]+$'"
        assert _scalar(sql) is True

    def test_unknown_row_present(self):
        sql = "select count(*) from (select 0::bigint as k, 'UNKNOWN' as n) where n = 'UNKNOWN'"
        assert _scalar(sql) == 1


# ---------------------------------------------------------------------------
# fact_sales_by_employee — aggregation logic
# ---------------------------------------------------------------------------

FACT_EMPLOYEE_SQL = """
with orders as (
    select * from (values
        -- sale_date, store_name, employee_name, net_sales, order_id, tip_amount, tax_amount, discount_total
        ('2025-01-01'::date, 'TAMPA', 'ALICE',   120.00, 'O001', 2.0, 9.60, 0.0),
        ('2025-01-01'::date, 'TAMPA', 'ALICE',    80.00, 'O002', 1.5, 6.40, 5.0),
        ('2025-01-01'::date, 'TAMPA', 'BOB',      60.00, 'O003', 0.0, 4.80, 0.0),
        ('2025-01-01'::date, 'TAMPA',  null,      40.00, 'O004', 0.0, 3.20, 0.0)
    ) t(sale_date, store_name, employee_name, net_sales, order_id, tip_amount, tax_amount, discount_total)
),
dim_date as (
    select cast(strftime(DATE '2025-01-01', '%Y%m%d') as integer) as date_key, DATE '2025-01-01' as date
),
dim_store as (
    select 5001::bigint as store_key, 'TAMPA' as store_name
),
dim_employee as (
    select 101::bigint as employee_key, 'ALICE'   as employee_name
    union all select 102::bigint,       'BOB'
    union all select 0::bigint,         'UNKNOWN'
),
joined as (
    select
        d.date_key,
        s.store_key,
        coalesce(emp.employee_key, 0) as employee_key,
        o.net_sales,
        o.order_id,
        o.tip_amount,
        o.tax_amount,
        o.discount_total
    from orders o
    inner join dim_date     d   on o.sale_date                          = d.date
    inner join dim_store    s   on o.store_name                         = s.store_name
    left  join dim_employee emp on coalesce(o.employee_name, 'UNKNOWN') = emp.employee_name
)
select
    date_key,
    store_key,
    employee_key,
    sum(net_sales)                                                              as net_sales,
    count(distinct order_id)                                                    as order_count,
    sum(tip_amount)                                                             as tip_amount,
    sum(tax_amount)                                                             as tax_amount,
    sum(discount_total)                                                         as discount_total,
    round((sum(net_sales) / nullif(count(distinct order_id), 0))::numeric, 2)  as avg_ticket
from joined
group by date_key, store_key, employee_key
order by employee_key
"""


@pytest.fixture(scope="module")
def fact_employee():
    con = duckdb.connect()
    return con.execute(FACT_EMPLOYEE_SQL).df()


class TestFactSalesByEmployee:
    def test_three_rows_alice_bob_unknown(self, fact_employee):
        assert len(fact_employee) == 3

    def test_alice_net_sales(self, fact_employee):
        alice = fact_employee[fact_employee["employee_key"] == 101].iloc[0]
        assert float(alice["net_sales"]) == pytest.approx(200.0)

    def test_alice_order_count(self, fact_employee):
        alice = fact_employee[fact_employee["employee_key"] == 101].iloc[0]
        assert int(alice["order_count"]) == 2

    def test_alice_avg_ticket(self, fact_employee):
        alice = fact_employee[fact_employee["employee_key"] == 101].iloc[0]
        assert float(alice["avg_ticket"]) == pytest.approx(100.0)

    def test_alice_tip_summed(self, fact_employee):
        alice = fact_employee[fact_employee["employee_key"] == 101].iloc[0]
        assert float(alice["tip_amount"]) == pytest.approx(3.5)

    def test_alice_discount_summed(self, fact_employee):
        alice = fact_employee[fact_employee["employee_key"] == 101].iloc[0]
        assert float(alice["discount_total"]) == pytest.approx(5.0)

    def test_bob_net_sales(self, fact_employee):
        bob = fact_employee[fact_employee["employee_key"] == 102].iloc[0]
        assert float(bob["net_sales"]) == pytest.approx(60.0)

    def test_null_employee_falls_back_to_unknown(self, fact_employee):
        unknown = fact_employee[fact_employee["employee_key"] == 0].iloc[0]
        assert float(unknown["net_sales"]) == pytest.approx(40.0)

    def test_unique_key_is_date_store_employee(self, fact_employee):
        assert len(fact_employee) == fact_employee[["date_key", "store_key", "employee_key"]].drop_duplicates().__len__()
