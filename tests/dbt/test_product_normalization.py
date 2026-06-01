"""
Unit tests for product_name and product_canonical_name normalization logic.

Both normalizations are reproduced as DuckDB SQL expressions — the same
logic used in stg_par2, stg_ls2, and dim_product — so we can validate
every edge case without a live Postgres connection.

Key rules under test:
  PAR:  strip leading  "NN OZ " prefix  →  "16 OZ ICED LATTE"  →  "ICED LATTE"
  LS2:  strip trailing "(NN OZ) [SML]"  →  "ICED LATTE (16 OZ) M"  →  "ICED LATTE"
  Both: UPPER + TRIM applied first; HOT / ICED / COLD suffixes preserved.
"""

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


PAR_CANON_EXPR = """
select regexp_replace(upper(trim(?)), '^[0-9]+\\s*OZ\\s+', '')
"""

LS2_CANON_EXPR = """
select regexp_replace(upper(trim(?)), '\\s*\\(\\s*[0-9]+\\s*OZ\\s*\\)\\s*[A-Za-z]{0,3}\\s*$', '')
"""


def _par_canon(name: str) -> str:
    con = duckdb.connect()
    return con.execute(PAR_CANON_EXPR, [name]).fetchone()[0]


def _ls2_canon(name: str) -> str:
    con = duckdb.connect()
    return con.execute(LS2_CANON_EXPR, [name]).fetchone()[0]


# ---------------------------------------------------------------------------
# PAR normalization
# ---------------------------------------------------------------------------


class TestParCanonicalName:
    # ── Standard size variants collapse to the same canonical ──────────────

    def test_strips_16oz_prefix(self):
        assert _par_canon("16 OZ ICED LATTE") == "ICED LATTE"

    def test_strips_20oz_prefix(self):
        assert _par_canon("20 OZ ICED LATTE") == "ICED LATTE"

    def test_strips_24oz_prefix(self):
        assert _par_canon("24 OZ ICED LATTE") == "ICED LATTE"

    def test_strips_32oz_prefix(self):
        assert _par_canon("32 OZ ICED LATTE") == "ICED LATTE"

    def test_strips_12oz_prefix(self):
        assert _par_canon("12 OZ ICED LATTE") == "ICED LATTE"

    def test_all_sizes_of_iced_latte_same_canonical(self):
        sizes = [
            "12 OZ ICED LATTE", "16 OZ ICED LATTE",
            "20 OZ ICED LATTE", "24 OZ ICED LATTE", "32 OZ ICED LATTE",
        ]
        assert len({_par_canon(s) for s in sizes}) == 1

    def test_strips_small_oz(self):
        assert _par_canon("4 OZ ESPRESSO") == "ESPRESSO"

    def test_strips_oz_without_space(self):
        # e.g. "96OZ CARAFE DRIP"
        assert _par_canon("96OZ CARAFE DRIP") == "CARAFE DRIP"

    # ── HOT / ICED / COLD suffixes are distinct products — must be preserved ─

    def test_preserves_hot_suffix(self):
        assert _par_canon("20 OZ CHAI TEA LATTE HOT") == "CHAI TEA LATTE HOT"

    def test_preserves_iced_suffix(self):
        assert _par_canon("20 OZ CHAI TEA LATTE ICED") == "CHAI TEA LATTE ICED"

    def test_hot_and_iced_are_different_canonicals(self):
        hot  = _par_canon("16 OZ DRIP COFFEE HOT")
        iced = _par_canon("16 OZ ICED DRIP COFFEE")
        assert hot != iced

    def test_cold_brew_preserved(self):
        assert _par_canon("20 OZ COLD BREW") == "COLD BREW"

    # ── Food / retail items (no size prefix) pass through unchanged ────────

    def test_food_item_unchanged(self):
        assert _par_canon("QARGO CLASSIC") == "QARGO CLASSIC"

    def test_food_with_ampersand_unchanged(self):
        assert _par_canon("CHEDDAR & CRISP") == "CHEDDAR & CRISP"

    def test_food_croissant_unchanged(self):
        assert _par_canon("CHOCOLATE CROISSANT") == "CHOCOLATE CROISSANT"

    def test_retail_water_unchanged(self):
        assert _par_canon("ACQUA PANNA -STILL WATER GLASS 500ML") == "ACQUA PANNA -STILL WATER GLASS 500ML"

    # ── Embedded size (NOT a leading prefix) must NOT be stripped ──────────

    def test_embedded_size_not_stripped(self):
        # "ACAI 16 OZ" — size at end, not leading prefix
        assert _par_canon("ACAI 16 OZ") == "ACAI 16 OZ"

    # ── Items starting with digit but not a size prefix ────────────────────

    def test_1_scoop_unchanged(self):
        assert _par_canon("1 SCOOP") == "1 SCOOP"

    def test_2_scoops_unchanged(self):
        assert _par_canon("2 SCOOPS") == "2 SCOOPS"

    # ── Upper-casing applied ───────────────────────────────────────────────

    def test_output_is_always_uppercased(self):
        result = _par_canon("16 oz iced latte")
        assert result == result.upper()

    def test_mixed_case_input_uppercased(self):
        assert _par_canon("16 Oz Iced Latte") == "ICED LATTE"

    # ── Whitespace trimming ────────────────────────────────────────────────

    def test_leading_whitespace_trimmed(self):
        assert _par_canon("  16 OZ ICED LATTE") == "ICED LATTE"

    def test_trailing_whitespace_trimmed(self):
        assert _par_canon("16 OZ ICED LATTE  ") == "ICED LATTE"


# ---------------------------------------------------------------------------
# LS2 normalization
# ---------------------------------------------------------------------------


class TestLs2CanonicalName:
    # ── Standard suffix variants collapse to the same canonical ────────────

    def test_strips_medium_suffix(self):
        assert _ls2_canon("ICED LATTE (16 OZ) M") == "ICED LATTE"

    def test_strips_large_suffix(self):
        assert _ls2_canon("ICED LATTE (20 OZ) L") == "ICED LATTE"

    def test_strips_small_suffix(self):
        assert _ls2_canon("CAFFE LATTE (12 OZ) S") == "CAFFE LATTE"

    def test_strips_xl_suffix(self):
        assert _ls2_canon("ICED LATTE (24 OZ) XL") == "ICED LATTE"

    def test_strips_xxl_suffix(self):
        assert _ls2_canon("COLD BREW (32OZ) XXL") == "COLD BREW"

    def test_strips_no_size_letter(self):
        # No S/M/L after closing paren
        assert _ls2_canon("WINTERBERRY MATCHA (24 OZ)") == "WINTERBERRY MATCHA"

    def test_strips_oz_without_space(self):
        assert _ls2_canon("ESPRESSO (4OZ)") == "ESPRESSO"

    def test_strips_extra_space_before_digits(self):
        assert _ls2_canon("GINGERBELL LATTE ( 16 OZ)") == "GINGERBELL LATTE"

    def test_strips_8oz_flat_white(self):
        assert _ls2_canon("FLAT WHITE (8 OZ)") == "FLAT WHITE"

    def test_strips_8oz_cortado(self):
        assert _ls2_canon("CORTADO (8 OZ)") == "CORTADO"

    def test_all_sizes_of_caffe_latte_same_canonical(self):
        sizes = [
            "CAFFE LATTE (12 OZ) S", "CAFFE LATTE (16 OZ) M",
            "CAFFE LATTE (20 OZ) L", "CAFFE LATTE (24 OZ) XL",
        ]
        assert len({_ls2_canon(s) for s in sizes}) == 1

    # ── Parentheses in the MIDDLE of the name must not be stripped ─────────

    def test_parentheses_in_middle_unchanged(self):
        name = "3 CHOCOLATE MOUSE (TASTE OF ITALY)"
        assert _ls2_canon(name) == name.upper()

    # ── Names without size suffix pass through unchanged ───────────────────

    def test_food_item_unchanged(self):
        assert _ls2_canon("QARGO CLASSIC") == "QARGO CLASSIC"

    def test_beverage_without_suffix_unchanged(self):
        assert _ls2_canon("ICED LATTE") == "ICED LATTE"

    def test_veggie_caprese_unchanged(self):
        assert _ls2_canon("VEGGIE CAPRESE") == "VEGGIE CAPRESE"

    def test_acai_embedded_size_unchanged(self):
        # "ACAI 16 OZ" has no surrounding parens — should pass through
        assert _ls2_canon("ACAI 16 OZ") == "ACAI 16 OZ"

    # ── Special characters in name ─────────────────────────────────────────

    def test_apostrophe_in_name(self):
        assert _ls2_canon("S'MORES MOCHA FRAPPE (20 OZ) L") == "S'MORES MOCHA FRAPPE"

    def test_dash_in_name(self):
        assert _ls2_canon("PINA COCO-LADA (16 OZ) M") == "PINA COCO-LADA"

    def test_ampersand_in_name(self):
        assert _ls2_canon("STRAWBERRIES & CREAM (16 OZ) M") == "STRAWBERRIES & CREAM"

    # ── Output always uppercased ───────────────────────────────────────────

    def test_output_always_uppercased(self):
        result = _ls2_canon("iced latte (16 oz) m")
        assert result == result.upper()


# ---------------------------------------------------------------------------
# Cross-system: PAR and LS2 must converge on the same canonical for the
# same conceptual product
# ---------------------------------------------------------------------------


class TestCrossSystemCanonical:
    def test_iced_latte_matches(self):
        assert _par_canon("16 OZ ICED LATTE") == _ls2_canon("ICED LATTE (16 OZ) M") == "ICED LATTE"

    def test_caffe_latte_matches(self):
        assert _par_canon("16 OZ CAFFE LATTE") == _ls2_canon("CAFFE LATTE (16 OZ) M") == "CAFFE LATTE"

    def test_espresso_matches(self):
        assert _par_canon("4 OZ ESPRESSO") == _ls2_canon("ESPRESSO (4OZ)") == "ESPRESSO"

    def test_drip_coffee_matches(self):
        assert _par_canon("16 OZ DRIP COFFEE HOT") == "DRIP COFFEE HOT"
        assert _ls2_canon("DRIP COFFEE (16 OZ) M") == "DRIP COFFEE"
        # HOT suffix in PAR makes these intentionally different — correct behavior

    def test_iced_matcha_latte_matches(self):
        assert _par_canon("16 OZ ICED MATCHA LATTE") == _ls2_canon("ICED MATCHA LATTE (16 OZ) M") == "ICED MATCHA LATTE"

    def test_cold_brew_matches(self):
        assert _par_canon("16 OZ COLD BREW") == _ls2_canon("COLD BREW (16 OZ) M") == "COLD BREW"

    def test_flat_white_matches(self):
        assert _par_canon("8 OZ FLAT WHITE") == _ls2_canon("FLAT WHITE (8 OZ)") == "FLAT WHITE"

    def test_cortado_matches(self):
        assert _par_canon("8 OZ CORTADO") == _ls2_canon("CORTADO (8 OZ)") == "CORTADO"

    def test_iced_mocha_matches(self):
        assert _par_canon("16 OZ ICED MOCHA") == _ls2_canon("ICED MOCHA (16 OZ) M") == "ICED MOCHA"

    def test_mother_of_dragons_matches(self):
        assert _par_canon("16 OZ MOTHER OF DRAGONS") == _ls2_canon("MOTHER OF DRAGONS (16 OZ) M") == "MOTHER OF DRAGONS"

    def test_food_items_always_match(self):
        foods = [
            "QARGO CLASSIC", "VEGGIE CAPRESE", "ALMOND CROISSANT",
            "FRENCH MACARONS", "CINNAMON ROLL", "BANANA NUT MUFFIN",
        ]
        for food in foods:
            assert _par_canon(food) == _ls2_canon(food) == food, food


# ---------------------------------------------------------------------------
# dim_product logic — derived dimension with both columns
# ---------------------------------------------------------------------------


DIM_PRODUCT_SQL = """
with par_products as (
    select * from (values
        -- product_name, product_canonical_name, revenue_center_name
        ('16 OZ ICED LATTE',    regexp_replace('16 OZ ICED LATTE',    '^[0-9]+\\s*OZ\\s+', ''), 'Beverage'),
        ('20 OZ ICED LATTE',    regexp_replace('20 OZ ICED LATTE',    '^[0-9]+\\s*OZ\\s+', ''), 'Beverage'),
        ('QARGO CLASSIC',       regexp_replace('QARGO CLASSIC',       '^[0-9]+\\s*OZ\\s+', ''), 'Food'),
        ('CHEDDAR & CRISP',     regexp_replace('CHEDDAR & CRISP',     '^[0-9]+\\s*OZ\\s+', ''), 'Food'),
        ('4 OZ ESPRESSO',       regexp_replace('4 OZ ESPRESSO',       '^[0-9]+\\s*OZ\\s+', ''), 'Beverage')
    ) t(product_name, product_canonical_name, revenue_center_name)
),
ls2_products as (
    select * from (values
        ('ICED LATTE',          regexp_replace('ICED LATTE',          '\\s*\\(\\s*[0-9]+\\s*OZ\\s*\\)\\s*[A-Za-z]{0,3}\\s*$', ''), 'Beverage'),
        ('ICED LATTE (16 OZ) M',regexp_replace('ICED LATTE (16 OZ) M','\\s*\\(\\s*[0-9]+\\s*OZ\\s*\\)\\s*[A-Za-z]{0,3}\\s*$', ''), 'Beverage'),
        ('QARGO CLASSIC',       regexp_replace('QARGO CLASSIC',       '\\s*\\(\\s*[0-9]+\\s*OZ\\s*\\)\\s*[A-Za-z]{0,3}\\s*$', ''), 'Food'),
        ('ESPRESSO (4OZ)',       regexp_replace('ESPRESSO (4OZ)',      '\\s*\\(\\s*[0-9]+\\s*OZ\\s*\\)\\s*[A-Za-z]{0,3}\\s*$', ''), 'Beverage')
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
def dim_product_new():
    con = duckdb.connect()
    return con.execute(DIM_PRODUCT_SQL).df()


class TestDimProductNew:
    def test_product_name_is_unique(self, dim_product_new):
        names = dim_product_new["product_name"].tolist()
        assert len(names) == len(set(names))

    def test_product_key_is_unique(self, dim_product_new):
        assert dim_product_new["product_key"].nunique() == len(dim_product_new)

    def test_no_null_product_name(self, dim_product_new):
        assert dim_product_new["product_name"].notna().all()

    def test_no_null_product_canonical_name(self, dim_product_new):
        assert dim_product_new["product_canonical_name"].notna().all()

    def test_no_null_revenue_center_name(self, dim_product_new):
        assert dim_product_new["revenue_center_name"].notna().all()

    def test_revenue_center_only_valid_values(self, dim_product_new):
        valid = {"Beverage", "Food", "Retail", "Other"}
        actual = set(dim_product_new["revenue_center_name"].tolist())
        assert actual.issubset(valid)

    def test_unknown_row_present_with_key_zero(self, dim_product_new):
        unknown = dim_product_new[dim_product_new["product_name"] == "UNKNOWN"]
        assert len(unknown) == 1
        assert int(unknown.iloc[0]["product_key"]) == 0

    def test_cross_system_deduplication(self, dim_product_new):
        # QARGO CLASSIC exists in both PAR and LS2 — must appear only once
        qargo = dim_product_new[dim_product_new["product_name"] == "QARGO CLASSIC"]
        assert len(qargo) == 1

    def test_par_size_variants_are_separate_rows(self, dim_product_new):
        # 16 OZ and 20 OZ are distinct product_name rows (different granularity)
        r16 = dim_product_new[dim_product_new["product_name"] == "16 OZ ICED LATTE"]
        r20 = dim_product_new[dim_product_new["product_name"] == "20 OZ ICED LATTE"]
        assert len(r16) == 1
        assert len(r20) == 1

    def test_par_size_variants_share_canonical(self, dim_product_new):
        r16 = dim_product_new[dim_product_new["product_name"] == "16 OZ ICED LATTE"].iloc[0]
        r20 = dim_product_new[dim_product_new["product_name"] == "20 OZ ICED LATTE"].iloc[0]
        assert r16["product_canonical_name"] == r20["product_canonical_name"] == "ICED LATTE"

    def test_ls2_size_variant_and_base_share_canonical(self, dim_product_new):
        base    = dim_product_new[dim_product_new["product_name"] == "ICED LATTE"].iloc[0]
        variant = dim_product_new[dim_product_new["product_name"] == "ICED LATTE (16 OZ) M"].iloc[0]
        assert base["product_canonical_name"] == variant["product_canonical_name"] == "ICED LATTE"

    def test_food_item_canonical_equals_name(self, dim_product_new):
        row = dim_product_new[dim_product_new["product_name"] == "QARGO CLASSIC"].iloc[0]
        assert row["product_canonical_name"] == "QARGO CLASSIC"


# ---------------------------------------------------------------------------
# dim_campaign logic
# ---------------------------------------------------------------------------


DIM_CAMPAIGN_SQL = """
with seed_data as (
    select * from (values
        ('ICED LATTE',         'SUMMER REFRESH 2025', DATE '2025-06-01', DATE '2025-08-31'),
        ('CAFFE LATTE',        'SUMMER REFRESH 2025', DATE '2025-06-01', DATE '2025-08-31'),
        ('QARGO CLASSIC',      'FLAGSHIP FOREVER',    NULL,              NULL)
    ) t(product_canonical_name, campaign_name, campaign_start_date, campaign_end_date)
    where campaign_name is not null and trim(campaign_name) <> ''
      and product_canonical_name is not null and trim(product_canonical_name) <> ''
)
select
    abs(hash(campaign_name)) as campaign_key,
    campaign_name,
    product_canonical_name,
    campaign_start_date,
    campaign_end_date
from seed_data
union all
select 0, 'NO CAMPAIGN', null, null, null
"""


@pytest.fixture(scope="module")
def dim_campaign():
    con = duckdb.connect()
    return con.execute(DIM_CAMPAIGN_SQL).df()


class TestDimCampaign:
    def test_no_null_campaign_key(self, dim_campaign):
        assert dim_campaign["campaign_key"].notna().all()

    def test_no_null_campaign_name(self, dim_campaign):
        assert dim_campaign["campaign_name"].notna().all()

    def test_no_campaign_row_present(self, dim_campaign):
        no_camp = dim_campaign[dim_campaign["campaign_name"] == "NO CAMPAIGN"]
        assert len(no_camp) == 1
        assert int(no_camp.iloc[0]["campaign_key"]) == 0

    def test_campaign_key_consistent_for_same_name(self, dim_campaign):
        # Both ICED LATTE and CAFFE LATTE belong to SUMMER REFRESH 2025 — same campaign_key
        rows = dim_campaign[dim_campaign["campaign_name"] == "SUMMER REFRESH 2025"]
        assert rows["campaign_key"].nunique() == 1

    def test_permanent_campaign_has_null_dates(self, dim_campaign):
        flagship = dim_campaign[dim_campaign["campaign_name"] == "FLAGSHIP FOREVER"]
        assert len(flagship) == 1
        assert flagship.iloc[0]["campaign_start_date"] is None or str(flagship.iloc[0]["campaign_start_date"]) in ("None", "NaT", "")

    def test_timed_campaign_has_dates(self, dim_campaign):
        summer = dim_campaign[dim_campaign["product_canonical_name"] == "ICED LATTE"]
        assert len(summer) == 1


# ---------------------------------------------------------------------------
# fact_sales join behavior with new product_name grain
# ---------------------------------------------------------------------------


FACT_SALES_NEW_SQL = """
with orders as (
    select * from (values
        -- sale_date, store_name, net_sales, order_id, tip, destination, tax, discount, product_name
        (DATE '2025-01-01', 'BERKELEY', 10.00, 'A001', 0.0, 'DINE IN', 0.80, 0.00, '16 OZ ICED LATTE'),
        (DATE '2025-01-01', 'BERKELEY', 15.00, 'A002', 1.0, 'DINE IN', 1.20, 0.50, '20 OZ ICED LATTE'),
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
    select abs(hash('BERKELEY')) as store_key, 'BERKELEY' as store_name
),
dim_product as (
    select abs(hash('16 OZ ICED LATTE')) as product_key, '16 OZ ICED LATTE' as product_name, 'ICED LATTE' as product_canonical_name, 'Beverage' as revenue_center_name
    union all
    select abs(hash('20 OZ ICED LATTE')), '20 OZ ICED LATTE', 'ICED LATTE', 'Beverage'
    union all
    select abs(hash('QARGO CLASSIC')),    'QARGO CLASSIC',    'QARGO CLASSIC', 'Food'
    union all
    select 0, 'UNKNOWN', 'UNKNOWN', 'Other'
),
dim_destination as (
    select abs(hash('DINE IN')) as destination_key, 'DINE IN' as destination_name
    union all select abs(hash('TO GO')), 'TO GO'
    union all select 0, 'UNKNOWN'
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
    inner join dim_date        d    on o.sale_date                        = d.date
    inner join dim_store       s    on o.store_name                       = s.store_name
    left  join dim_product     p    on upper(trim(o.product_name))        = p.product_name
    left  join dim_destination dest on coalesce(o.destination, 'UNKNOWN') = dest.destination_name
)
select
    date_key,
    store_key,
    product_key,
    destination_key,
    sum(net_sales)                                                             as net_sales,
    count(distinct order_id)                                                   as order_count,
    sum(tip_amount)                                                            as tip_amount,
    sum(tax_amount)                                                            as tax_amount,
    sum(discount_total)                                                        as discount_total,
    round((sum(net_sales) / nullif(count(distinct order_id), 0))::numeric, 2) as avg_ticket
from joined
group by date_key, store_key, product_key, destination_key
order by date_key, product_key
"""


@pytest.fixture(scope="module")
def fact_sales_new():
    con = duckdb.connect()
    return con.execute(FACT_SALES_NEW_SQL).df()


class TestFactSalesProductGrain:
    def test_three_rows_output(self, fact_sales_new):
        # Jan 1: 16 OZ ICED LATTE, Jan 1: 20 OZ ICED LATTE, Jan 2: QARGO CLASSIC
        assert len(fact_sales_new) == 3

    def test_16oz_iced_latte_net_sales(self, fact_sales_new):
        # Orders A001 (x2) sum to 10+5=15
        p_key = _scalar(f"select abs(hash('16 OZ ICED LATTE'))")
        row = fact_sales_new[fact_sales_new["product_key"] == p_key]
        assert len(row) == 1
        assert float(row.iloc[0]["net_sales"]) == pytest.approx(15.0)

    def test_20oz_iced_latte_net_sales(self, fact_sales_new):
        p_key = _scalar(f"select abs(hash('20 OZ ICED LATTE'))")
        row = fact_sales_new[fact_sales_new["product_key"] == p_key]
        assert float(row.iloc[0]["net_sales"]) == pytest.approx(15.0)

    def test_order_count_is_distinct_orders_per_product(self, fact_sales_new):
        # 16 OZ ICED LATTE appears in A001 twice → still 1 distinct order
        p_key = _scalar(f"select abs(hash('16 OZ ICED LATTE'))")
        row = fact_sales_new[fact_sales_new["product_key"] == p_key]
        assert int(row.iloc[0]["order_count"]) == 1

    def test_food_row_correct(self, fact_sales_new):
        p_key = _scalar(f"select abs(hash('QARGO CLASSIC'))")
        row = fact_sales_new[fact_sales_new["product_key"] == p_key]
        assert float(row.iloc[0]["net_sales"]) == pytest.approx(8.0)
        assert int(row.iloc[0]["order_count"]) == 1

    def test_unique_key_per_grain(self, fact_sales_new):
        cols = ["date_key", "store_key", "product_key", "destination_key"]
        assert len(fact_sales_new) == len(fact_sales_new[cols].drop_duplicates())

    def test_no_orphaned_product_keys(self, fact_sales_new):
        # coalesce(p.product_key, 0) must be applied — no NULL product_keys in fact
        assert fact_sales_new["product_key"].notna().all()

    def test_product_name_join_not_revenue_center(self):
        # Confirm that joining on product_name (not revenue_center) gives correct
        # granularity: 16 OZ and 20 OZ are SEPARATE rows, not aggregated into one
        sql = f"""
        select count(distinct product_key)
        from ({FACT_SALES_NEW_SQL})
        where date_key = cast(strftime(DATE '2025-01-01', '%Y%m%d') as integer)
        """
        # Should be 2 (16 OZ and 20 OZ are different product_keys)
        assert _scalar(sql) == 2


# ---------------------------------------------------------------------------
# Campaign join query pattern
# ---------------------------------------------------------------------------


class TestCampaignJoinPattern:
    def test_product_in_active_campaign_returns_campaign(self):
        sql = """
        with dim_product as (
            select 'ICED LATTE' as product_canonical_name
        ),
        dim_campaign as (
            select 'SUMMER REFRESH 2025' as campaign_name,
                   'ICED LATTE'          as product_canonical_name,
                   DATE '2025-06-01'     as campaign_start_date,
                   DATE '2025-08-31'     as campaign_end_date
        )
        select c.campaign_name
        from dim_product p
        left join dim_campaign c
               on p.product_canonical_name = c.product_canonical_name
              and (c.campaign_start_date is null or DATE '2025-07-15' >= c.campaign_start_date)
              and (c.campaign_end_date   is null or DATE '2025-07-15' <= c.campaign_end_date)
        """
        assert _scalar(sql) == "SUMMER REFRESH 2025"

    def test_product_outside_campaign_dates_returns_null(self):
        sql = """
        with dim_product as (
            select 'ICED LATTE' as product_canonical_name
        ),
        dim_campaign as (
            select 'SUMMER REFRESH 2025' as campaign_name,
                   'ICED LATTE'          as product_canonical_name,
                   DATE '2025-06-01'     as campaign_start_date,
                   DATE '2025-08-31'     as campaign_end_date
        )
        select c.campaign_name
        from dim_product p
        left join dim_campaign c
               on p.product_canonical_name = c.product_canonical_name
              and (c.campaign_start_date is null or DATE '2025-10-01' >= c.campaign_start_date)
              and (c.campaign_end_date   is null or DATE '2025-10-01' <= c.campaign_end_date)
        """
        assert _scalar(sql) is None

    def test_permanent_campaign_always_matches(self):
        sql = """
        with dim_product as (
            select 'QARGO CLASSIC' as product_canonical_name
        ),
        dim_campaign as (
            select 'FLAGSHIP FOREVER'    as campaign_name,
                   'QARGO CLASSIC'       as product_canonical_name,
                   NULL::date            as campaign_start_date,
                   NULL::date            as campaign_end_date
        )
        select c.campaign_name
        from dim_product p
        left join dim_campaign c
               on p.product_canonical_name = c.product_canonical_name
              and (c.campaign_start_date is null or DATE '2030-01-01' >= c.campaign_start_date)
              and (c.campaign_end_date   is null or DATE '2030-01-01' <= c.campaign_end_date)
        """
        assert _scalar(sql) == "FLAGSHIP FOREVER"

    def test_product_not_in_any_campaign_returns_null(self):
        sql = """
        with dim_product as (
            select 'HOT CHOCOLATE' as product_canonical_name
        ),
        dim_campaign as (
            select 'SUMMER REFRESH'     as campaign_name,
                   'ICED LATTE'         as product_canonical_name,
                   NULL::date           as campaign_start_date,
                   NULL::date           as campaign_end_date
        )
        select c.campaign_name
        from dim_product p
        left join dim_campaign c
               on p.product_canonical_name = c.product_canonical_name
              and (c.campaign_start_date is null or DATE '2025-07-01' >= c.campaign_start_date)
              and (c.campaign_end_date   is null or DATE '2025-07-01' <= c.campaign_end_date)
        """
        assert _scalar(sql) is None
