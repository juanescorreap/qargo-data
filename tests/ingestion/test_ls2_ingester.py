"""Unit tests for LS2CSVIngester and _store_name_from_ls_filename — no database required."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from ingestion.sources.csv import LS2CSVIngester, _store_name_from_ls_filename

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LS2_HEADER = (
    '"Identifier";"PeriodId";"YearId";"Device_Name";"Passive_Device";'
    '"Date";"Mode";"Account";"AccountName";"Staff";"Reference";"Type";'
    '"Qty";"UnitPrice";"FinalPrice";"Discount";"Loss";"Comp";"Charge";'
    '"SKU";"Item";"Group";"StatGroup";"TaxName";"TaxRate";"PreTax";'
    '"TaxAmount";"Profile"'
)

LS2_FNAME = "qargocoffee-hqaccount_qargocoffeeberkeley_transactions_20260401_20260501.csv"


def _row(
    date_str: str = "4/1/26 9:00 AM",
    account: str = "A883046.001",
    type_: str = "SALE",
    final_price: str = "5.50",
    group: str = "Beverages(1024306750423249)",
) -> str:
    return (
        f'"ID1";"P1";"Y1";"iPad";"iPad";"{date_str}";"Prod";"{account}";'
        f'"Customer";"Staff";"Ref1";"{type_}";"1";"5.50";"{final_price}";'
        f'"0";"0";"0";"0";"SKU1";"Latte";"{group}";"Beverages";'
        f'"No tax";"1";"5.50";"0";"Dine-in"'
    )


def _write_ls2(
    tmp_path: Path,
    rows: list[str],
    fname: str = LS2_FNAME,
) -> Path:
    f = tmp_path / fname
    f.write_text(LS2_HEADER + "\n" + "\n".join(rows), encoding="latin-1")
    return f


INGESTER = LS2CSVIngester()


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_source_name(self):
        assert INGESTER.source_name == "ls2"

    def test_target_table(self):
        assert INGESTER.target_table == "raw_ls2"

    def test_date_column(self):
        assert INGESTER.date_column == "Date"


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


class TestListFiles:
    def test_matches_transaction_pattern(self, tmp_path):
        (tmp_path / LS2_FNAME).touch()
        files = INGESTER.list_files(tmp_path)
        assert len(files) == 1
        assert files[0].name == LS2_FNAME

    def test_ignores_par2_ddbb_files(self, tmp_path):
        (tmp_path / "DDBB_Jan_25.csv").touch()
        assert INGESTER.list_files(tmp_path) == []

    def test_ignores_unrelated_csv(self, tmp_path):
        (tmp_path / "report.csv").touch()
        assert INGESTER.list_files(tmp_path) == []

    def test_multiple_files_sorted(self, tmp_path):
        names = [
            "qargocoffee-hqaccount_qargocoffeeberkeley_transactions_20260601_20260701.csv",
            "qargocoffee-hqaccount_qargocoffeeberkeley_transactions_20260401_20260501.csv",
            "qargocoffee-hqaccount_qargocoffeeberkeley_transactions_20260501_20260601.csv",
        ]
        for n in names:
            (tmp_path / n).touch()
        result = [f.name for f in INGESTER.list_files(tmp_path)]
        assert result == sorted(names)

    def test_empty_directory(self, tmp_path):
        assert INGESTER.list_files(tmp_path) == []


# ---------------------------------------------------------------------------
# extract_file — type filtering
# ---------------------------------------------------------------------------


class TestTypeFiltering:
    def test_sale_rows_kept(self, tmp_path):
        f = _write_ls2(tmp_path, [_row(type_="SALE")])
        df = INGESTER.extract_file(f)
        assert len(df) == 1

    def test_update_rows_kept(self, tmp_path):
        f = _write_ls2(tmp_path, [_row(type_="UPDATE")])
        df = INGESTER.extract_file(f)
        assert len(df) == 1

    def test_transitory_comp_filtered(self, tmp_path):
        f = _write_ls2(tmp_path, [_row(type_="TRANSITORY_COMP")])
        df = INGESTER.extract_file(f)
        assert df.empty

    def test_transitory_open_filtered(self, tmp_path):
        f = _write_ls2(tmp_path, [_row(type_="TRANSITORY_OPEN")])
        df = INGESTER.extract_file(f)
        assert df.empty

    def test_void_filtered(self, tmp_path):
        f = _write_ls2(tmp_path, [_row(type_="VOID")])
        df = INGESTER.extract_file(f)
        assert df.empty

    def test_mixed_types_correct_count(self, tmp_path):
        rows = [
            _row(type_="SALE"),
            _row(type_="TRANSITORY_COMP"),
            _row(type_="VOID"),
            _row(type_="UPDATE"),
            _row(type_="TRANSITORY_OPEN"),
        ]
        f = _write_ls2(tmp_path, rows)
        df = INGESTER.extract_file(f)
        assert len(df) == 2
        assert set(df["Type"].unique()) == {"SALE", "UPDATE"}

    def test_all_transitory_returns_empty(self, tmp_path):
        rows = [_row(type_="TRANSITORY_COMP"), _row(type_="TRANSITORY_OPEN")]
        f = _write_ls2(tmp_path, rows)
        df = INGESTER.extract_file(f)
        assert df.empty


# ---------------------------------------------------------------------------
# extract_file — date parsing
# ---------------------------------------------------------------------------


class TestExtractDate:
    def test_date_parsed_to_date_object(self, tmp_path):
        f = _write_ls2(tmp_path, [_row(date_str="4/1/26 9:00 AM")])
        df = INGESTER.extract_file(f)
        assert df["Date"].iloc[0] == date(2026, 4, 1)

    def test_two_digit_year_interpreted_correctly(self, tmp_path):
        # pandas strptime: %y 00–68 → 2000–2068, 69–99 → 1969–1999
        f = _write_ls2(tmp_path, [_row(date_str="1/15/25 10:30 AM")])
        df = INGESTER.extract_file(f)
        assert df["Date"].iloc[0] == date(2025, 1, 15)

    def test_midnight_record(self, tmp_path):
        f = _write_ls2(tmp_path, [_row(date_str="12/31/25 12:00 AM")])
        df = INGESTER.extract_file(f)
        assert df["Date"].iloc[0] == date(2025, 12, 31)

    def test_date_is_python_date(self, tmp_path):
        f = _write_ls2(tmp_path, [_row()])
        df = INGESTER.extract_file(f)
        assert isinstance(df["Date"].iloc[0], date)


# ---------------------------------------------------------------------------
# extract_file — location from filename
# ---------------------------------------------------------------------------


class TestExtractLocation:
    def test_location_injected_from_filename(self, tmp_path):
        f = _write_ls2(tmp_path, [_row()])
        df = INGESTER.extract_file(f)
        assert df["Location"].iloc[0] == "Qargo Coffee Berkeley"

    def test_all_rows_get_same_location(self, tmp_path):
        rows = [_row(), _row(), _row()]
        f = _write_ls2(tmp_path, rows)
        df = INGESTER.extract_file(f)
        assert (df["Location"] == "Qargo Coffee Berkeley").all()


# ---------------------------------------------------------------------------
# extract_file — metadata columns
# ---------------------------------------------------------------------------


class TestExtractMetadata:
    def test_source_system_is_ls2(self, tmp_path):
        f = _write_ls2(tmp_path, [_row()])
        df = INGESTER.extract_file(f)
        assert df["_source_system"].iloc[0] == "ls2"

    def test_source_file_contains_filename(self, tmp_path):
        f = _write_ls2(tmp_path, [_row()])
        df = INGESTER.extract_file(f)
        assert df["_source_file"].iloc[0] == LS2_FNAME

    def test_ingested_at_present(self, tmp_path):
        f = _write_ls2(tmp_path, [_row()])
        df = INGESTER.extract_file(f)
        assert "_ingested_at" in df.columns
        assert df["_ingested_at"].notna().all()


# ---------------------------------------------------------------------------
# _store_name_from_ls_filename
# ---------------------------------------------------------------------------


class TestStoreNameFromFilename:
    def test_berkeley(self):
        fname = "qargocoffee-hqaccount_qargocoffeeberkeley_transactions_20260401_20260501.csv"
        assert _store_name_from_ls_filename(fname) == "Qargo Coffee Berkeley"

    def test_unknown_when_pattern_absent(self):
        assert _store_name_from_ls_filename("completely_different.csv") == "Unknown"

    def test_empty_string(self):
        assert _store_name_from_ls_filename("") == "Unknown"

    def test_hyphenated_slug_returns_unknown(self):
        # \w+ stops at '-', so a slug like "las-vegas" does NOT match the pattern.
        # The regex requires _transactions to follow immediately after \w+, but here
        # there is "-vegas_transactions". The function returns "Unknown" in this case.
        fname = "qargocoffee-hqaccount_qargocoffeelas-vegas_transactions_20260401_20260501.csv"
        result = _store_name_from_ls_filename(fname)
        assert result == "Unknown"

    def test_numeric_suffix_in_slug(self):
        fname = "qargocoffee-hqaccount_qargocoffeelab01_transactions_20260401_20260501.csv"
        result = _store_name_from_ls_filename(fname)
        assert result == "Qargo Coffee Lab01"

    def test_prefix_always_present(self):
        fname = "qargocoffee-hqaccount_qargocoffeedowntown_transactions_20260401_20260501.csv"
        result = _store_name_from_ls_filename(fname)
        assert result.startswith("Qargo Coffee ")
