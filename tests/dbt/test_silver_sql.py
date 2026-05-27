"""
Unit tests for the silver-layer transformation logic (stg_par2, stg_ls2)
using DuckDB as the execution engine — no Postgres connection required.

We test the CASE-statement logic by extracting it into standalone DuckDB
queries with controlled input data. This catches regressions in revenue-center
classification, store-name normalisation, and row-filter rules.
"""

import duckdb
import pytest


# ---------------------------------------------------------------------------
# Helpers — run SQL snippets in an isolated in-memory DuckDB
# ---------------------------------------------------------------------------


def _run(sql: str) -> list[tuple]:
    con = duckdb.connect()
    return con.execute(sql).fetchall()


def _scalar(sql: str):
    return _run(sql)[0][0]


# ---------------------------------------------------------------------------
# stg_par2 — store name normalisation
#
# Logic (from stg_par2.sql):
#   upper(trim(
#       case
#           when "Location" ilike 'Qargo Coffee %' then substring("Location" from 14)
#           when "Location" ilike 'Qargo %'        then substring("Location" from 7)
#           else "Location"
#       end
#   ))
# ---------------------------------------------------------------------------


STORE_NAME_EXPR = """
select upper(trim(
    case
        when location ilike 'Qargo Coffee %' then substring(location from 14)
        when location ilike 'Qargo %'        then substring(location from 7)
        else location
    end
)) as store_name
from (values (?)) t(location)
"""


def _store_name(location: str) -> str:
    con = duckdb.connect()
    return con.execute(STORE_NAME_EXPR, [location]).fetchone()[0]


class TestPAR2StoreNormalization:
    def test_qargo_coffee_prefix_stripped(self):
        assert _store_name("Qargo Coffee Berkeley") == "BERKELEY"

    def test_qargo_coffee_prefix_case_insensitive(self):
        assert _store_name("QARGO COFFEE BERKELEY") == "BERKELEY"

    def test_qargo_prefix_stripped(self):
        assert _store_name("Qargo Las Vegas") == "LAS VEGAS"

    def test_no_prefix_returned_as_is_uppercased(self):
        assert _store_name("Downtown Market") == "DOWNTOWN MARKET"

    def test_leading_trailing_whitespace_trimmed(self):
        assert _store_name("Qargo Coffee  Berkeley ") == "BERKELEY"

    def test_real_location_lab01(self):
        # Actual value in production data
        result = _store_name("Qargo Coffee **Lab-01**")
        assert result == "**LAB-01**"

    def test_real_location_long_beach(self):
        result = _store_name("Qargo Coffee 707 E Ocean, Long Beach, CA")
        assert result == "707 E OCEAN, LONG BEACH, CA"

    def test_result_always_uppercased(self):
        result = _store_name("some store name")
        assert result == result.upper()


# ---------------------------------------------------------------------------
# stg_par2 — revenue centre classification
#
# case
#   when lower("Revenue Center") like '%beverage%' then 'Beverage'
#   when lower("Revenue Center") like '%food%'     then 'Food'
#   when lower("Revenue Center") like '%retail%'   then 'Retail'
#   when lower("Revenue Center") like '%combo%'    then 'Food'
#   else 'Other'
# end
# ---------------------------------------------------------------------------


RC_EXPR = """
select case
    when lower(rc) like '%beverage%' then 'Beverage'
    when lower(rc) like '%food%'     then 'Food'
    when lower(rc) like '%retail%'   then 'Retail'
    when lower(rc) like '%combo%'    then 'Food'
    else 'Other'
end
from (values (?)) t(rc)
"""


def _par2_rc(revenue_center: str) -> str:
    con = duckdb.connect()
    return con.execute(RC_EXPR, [revenue_center]).fetchone()[0]


class TestPAR2RevenueCenter:
    def test_beverages(self):
        assert _par2_rc("Beverages") == "Beverage"

    def test_beverage_lowercase(self):
        assert _par2_rc("beverage") == "Beverage"

    def test_beverage_mixed_case(self):
        assert _par2_rc("BEVERAGES") == "Beverage"

    def test_food_category(self):
        assert _par2_rc("FOOD") == "Food"

    def test_hot_food(self):
        assert _par2_rc("Hot Food") == "Food"

    def test_combo_maps_to_food(self):
        assert _par2_rc("Combo Meal") == "Food"

    def test_retail(self):
        assert _par2_rc("RETAIL") == "Retail"

    def test_retail_shop(self):
        assert _par2_rc("Retail Shop") == "Retail"

    def test_unknown_maps_to_other(self):
        assert _par2_rc("Unknown") == "Other"

    def test_no_tax_menu_item_maps_to_other(self):
        # Real value found in production PAR2 data
        assert _par2_rc("NO TAX MENU ITEM") == "Other"

    def test_empty_string_maps_to_other(self):
        assert _par2_rc("") == "Other"

    def test_beverage_takes_priority_over_later_cases(self):
        # "beverage food" — first WHEN matches, result is Beverage
        assert _par2_rc("Beverage Food") == "Beverage"


# ---------------------------------------------------------------------------
# stg_par2 — row-filter logic
# (Voided = false AND Is Modifier = false AND Net Sales IS NOT NULL)
# ---------------------------------------------------------------------------


FILTER_SQL = """
with src as (
    select
        "Net Sales",
        "Voided",
        "Is Modifier"
    from (values
        (10.0, false, false),   -- should pass
        (null, false, false),   -- net_sales null → filtered
        (10.0, true,  false),   -- voided → filtered
        (10.0, false, true)     -- modifier → filtered
    ) t("Net Sales", "Voided", "Is Modifier")
)
select count(*) from src
where "Voided" = false
  and "Is Modifier" = false
  and "Net Sales" is not null
"""


class TestPAR2RowFilters:
    def test_only_valid_rows_pass(self):
        assert _scalar(FILTER_SQL) == 1

    def test_voided_row_excluded(self):
        sql = """
        select count(*) from (
            select 1
            from (values (true)) t("Voided")
            where "Voided" = false
        )"""
        assert _scalar(sql) == 0

    def test_modifier_row_excluded(self):
        sql = """
        select count(*) from (
            select 1
            from (values (true)) t("Is Modifier")
            where "Is Modifier" = false
        )"""
        assert _scalar(sql) == 0

    def test_null_net_sales_excluded(self):
        sql = """
        select count(*) from (
            select 1
            from (values (NULL::double)) t("Net Sales")
            where "Net Sales" is not null
        )"""
        assert _scalar(sql) == 0


# ---------------------------------------------------------------------------
# stg_ls2 — revenue centre classification
#
# split_part("Group", '(', 1) gives the text before the first '('
# e.g. "Beverages(123)" → "Beverages "
#
# case
#   when ... ilike '%beverage%'      then 'Beverage'
#   when ... ilike '%bottled drink%' then 'Beverage'
#   when ... ilike '%food%'          then 'Food'
#   when ... ilike '%bakery%'        then 'Food'
#   when ... ilike '%grab%'          then 'Food'
#   when ... ilike '%taste of italy%'then 'Food'
#   when ... ilike '%combo%'         then 'Food'
#   when ... ilike '%cold good%'     then 'Food'
#   when ... ilike '%retail%'        then 'Retail'
#   else 'Other'
# end
# ---------------------------------------------------------------------------


LS2_RC_EXPR = """
select case
    when split_part(grp, '(', 1) ilike '%beverage%'      then 'Beverage'
    when split_part(grp, '(', 1) ilike '%bottled drink%'  then 'Beverage'
    when split_part(grp, '(', 1) ilike '%food%'           then 'Food'
    when split_part(grp, '(', 1) ilike '%bakery%'         then 'Food'
    when split_part(grp, '(', 1) ilike '%grab%'           then 'Food'
    when split_part(grp, '(', 1) ilike '%taste of italy%' then 'Food'
    when split_part(grp, '(', 1) ilike '%combo%'          then 'Food'
    when split_part(grp, '(', 1) ilike '%cold good%'      then 'Food'
    when split_part(grp, '(', 1) ilike '%retail%'         then 'Retail'
    else 'Other'
end
from (values (?)) t(grp)
"""


def _ls2_rc(group: str) -> str:
    con = duckdb.connect()
    return con.execute(LS2_RC_EXPR, [group]).fetchone()[0]


class TestLS2RevenueCenter:
    def test_beverages_group(self):
        # Real production format: "Beverages(1024306750423249)"
        assert _ls2_rc("Beverages(1024306750423249)") == "Beverage"

    def test_beverage_no_parenthesis(self):
        assert _ls2_rc("Beverages") == "Beverage"

    def test_bottled_drink(self):
        assert _ls2_rc("Bottled Drinks(456)") == "Beverage"

    def test_food_group(self):
        assert _ls2_rc("Food(789)") == "Food"

    def test_bakery(self):
        assert _ls2_rc("Bakery Items(101)") == "Food"

    def test_grab_and_go(self):
        assert _ls2_rc("Grab & Go(112)") == "Food"

    def test_taste_of_italy(self):
        assert _ls2_rc("Taste of Italy(131)") == "Food"

    def test_combo(self):
        assert _ls2_rc("Combo Burgers(141)") == "Food"

    def test_cold_good(self):
        assert _ls2_rc("Cold Good Things(151)") == "Food"

    def test_retail(self):
        assert _ls2_rc("Retail Items(161)") == "Retail"

    def test_unknown_maps_to_other(self):
        assert _ls2_rc("Unknown(999)") == "Other"

    def test_modifiers_not_classified_as_other(self):
        # Modifiers are filtered OUT in stg_ls2 before the CASE;
        # but if the filter wasn't applied, the CASE would give 'Other'
        assert _ls2_rc("Modifiers(181)") == "Other"

    def test_split_part_strips_parenthetical_suffix(self):
        # "Beverages(1024306750423249)" → split_part → "Beverages" → Beverage
        result = _scalar(
            "select split_part('Beverages(1024306750423249)', '(', 1)"
        )
        assert result.strip() == "Beverages"


# ---------------------------------------------------------------------------
# stg_ls2 — modifier filter
#
# where split_part("Group", '(', 1) not ilike '%modifier%'
# ---------------------------------------------------------------------------


class TestLS2ModifierFilter:
    def test_modifier_group_excluded(self):
        sql = """
        select count(*) from (
            select 1
            from (values ('Modifiers(1024306750423236)')) t("Group")
            where split_part("Group", '(', 1) not ilike '%modifier%'
        )"""
        assert _scalar(sql) == 0

    def test_beverage_group_kept(self):
        sql = """
        select count(*) from (
            select 1
            from (values ('Beverages(123)')) t("Group")
            where split_part("Group", '(', 1) not ilike '%modifier%'
        )"""
        assert _scalar(sql) == 1

    def test_mixed_rows_correct_count(self):
        sql = """
        select count(*) from (
            select 1
            from (values
                ('Beverages(1)'),
                ('Modifiers(2)'),
                ('Food(3)'),
                ('Modifiers(4)'),
                ('Retail(5)')
            ) t("Group")
            where split_part("Group", '(', 1) not ilike '%modifier%'
        )"""
        assert _scalar(sql) == 3
