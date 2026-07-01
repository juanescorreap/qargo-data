"""Unit tests for PAR2CSVIngester — no database required."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from ingestion.sources.csv import PAR2CSVIngester

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PAR2_HEADER = (
    "Location,Closed Date/Time,Employee Name,Item ID,Item Name,Item PLU,"
    "Price,Discount Total,Promotion Total,Taxes,Net Sales,Gross Sales,"
    "Total Sales,Revenue Center,Has Employee Discount,Destination,Voided,"
    "Has Customer,Is Modifier,Order ID"
)


def _row(
    location="Qargo Coffee Berkeley",
    date_str="4/14/2025 5:09 PM",
    price="$5.00",
    discount="$0.00",
    promo="$0.00",
    taxes="$0.50",
    net_sales="$4.50",
    gross_sales="$5.00",
    total_sales="$5.50",
    revenue_center="Beverages",
    has_emp_discount="False",
    destination="Dine-in",
    voided="False",
    has_customer="True",
    is_modifier="False",
    order_id="ORD001",
) -> str:
    return (
        f'"{location}","{date_str}","John","I1","Latte","PLU1",'
        f'"{price}","{discount}","{promo}","{taxes}","{net_sales}",'
        f'"{gross_sales}","{total_sales}","{revenue_center}",'
        f'"{has_emp_discount}","{destination}","{voided}",'
        f'"{has_customer}","{is_modifier}","{order_id}"'
    )


def _write_par2(tmp_path: Path, rows: list[str], name: str = "DDBB_Jan_25.csv") -> Path:
    f = tmp_path / name
    f.write_text(PAR2_HEADER + "\n" + "\n".join(rows))
    return f


INGESTER = PAR2CSVIngester()


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_source_name(self):
        assert INGESTER.source_name == "par2"

    def test_target_table(self):
        assert INGESTER.target_table == "raw_par2_csv"

    def test_date_column(self):
        assert INGESTER.date_column == "Date"


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


class TestListFiles:
    def test_matches_ddbb_prefix(self, tmp_path):
        (tmp_path / "DDBB_Jan_25.csv").touch()
        (tmp_path / "DDBB_Feb_25.csv").touch()
        names = [f.name for f in INGESTER.list_files(tmp_path)]
        assert "DDBB_Jan_25.csv" in names
        assert "DDBB_Feb_25.csv" in names

    def test_ignores_ls2_files(self, tmp_path):
        (tmp_path / "qargocoffee-hqaccount_qargocoffeeberkeley_transactions_20260401_20260501.csv").touch()
        assert INGESTER.list_files(tmp_path) == []

    def test_ignores_other_csv(self, tmp_path):
        (tmp_path / "sales_report.csv").touch()
        (tmp_path / "other_file.csv").touch()
        assert INGESTER.list_files(tmp_path) == []

    def test_ignores_non_csv(self, tmp_path):
        (tmp_path / "DDBB_Jan_25.txt").touch()
        (tmp_path / "DDBB_Jan_25.xlsx").touch()
        assert INGESTER.list_files(tmp_path) == []

    def test_returns_sorted(self, tmp_path):
        for name in ["DDBB_Mar_25.csv", "DDBB_Jan_25.csv", "DDBB_Feb_25.csv"]:
            (tmp_path / name).touch()
        names = [f.name for f in INGESTER.list_files(tmp_path)]
        assert names == sorted(names)

    def test_empty_directory(self, tmp_path):
        assert INGESTER.list_files(tmp_path) == []

    def test_returns_path_objects(self, tmp_path):
        (tmp_path / "DDBB_Jan_25.csv").touch()
        files = INGESTER.list_files(tmp_path)
        assert all(isinstance(f, Path) for f in files)


# ---------------------------------------------------------------------------
# extract_file — date parsing
# ---------------------------------------------------------------------------


class TestExtractDate:
    def test_date_parsed_to_date_object(self, tmp_path):
        f = _write_par2(tmp_path, [_row(date_str="4/14/2025 5:09 PM")])
        df = INGESTER.extract_file(f)
        assert df["Date"].iloc[0] == date(2025, 4, 14)

    def test_date_noon(self, tmp_path):
        f = _write_par2(tmp_path, [_row(date_str="1/1/2025 12:00 PM")])
        df = INGESTER.extract_file(f)
        assert df["Date"].iloc[0] == date(2025, 1, 1)

    def test_date_midnight(self, tmp_path):
        f = _write_par2(tmp_path, [_row(date_str="12/31/2025 12:00 AM")])
        df = INGESTER.extract_file(f)
        assert df["Date"].iloc[0] == date(2025, 12, 31)

    def test_column_renamed_from_closed_datetime(self, tmp_path):
        f = _write_par2(tmp_path, [_row()])
        df = INGESTER.extract_file(f)
        assert "Date" in df.columns
        assert "Closed Date/Time" not in df.columns

    def test_date_is_python_date_not_datetime(self, tmp_path):
        f = _write_par2(tmp_path, [_row()])
        df = INGESTER.extract_file(f)
        assert isinstance(df["Date"].iloc[0], date)


# ---------------------------------------------------------------------------
# extract_file — currency stripping
# ---------------------------------------------------------------------------


class TestExtractCurrency:
    def test_dollar_sign_stripped(self, tmp_path):
        f = _write_par2(tmp_path, [_row(net_sales="$4.50")])
        df = INGESTER.extract_file(f)
        assert df["Net Sales"].iloc[0] == pytest.approx(4.50)

    def test_comma_stripped(self, tmp_path):
        f = _write_par2(tmp_path, [_row(net_sales="$1,000.00", price="$1,500.00")])
        df = INGESTER.extract_file(f)
        assert df["Net Sales"].iloc[0] == pytest.approx(1000.00)
        assert df["Price"].iloc[0] == pytest.approx(1500.00)

    def test_all_currency_columns_stripped(self, tmp_path):
        f = _write_par2(tmp_path, [_row(
            price="$5.00",
            discount="$0.50",
            promo="$0.25",
            taxes="$0.50",
            net_sales="$4.50",
            gross_sales="$5.00",
            total_sales="$5.50",
        )])
        df = INGESTER.extract_file(f)
        for col in ["Price", "Discount Total", "Promotion Total",
                    "Taxes", "Net Sales", "Gross Sales", "Total Sales"]:
            assert pd.api.types.is_numeric_dtype(df[col]), f"{col} should be numeric"

    def test_invalid_currency_coerced_to_nan(self, tmp_path):
        f = _write_par2(tmp_path, [_row(net_sales="N/A")])
        df = INGESTER.extract_file(f)
        assert pd.isna(df["Net Sales"].iloc[0])

    def test_zero_value_preserved(self, tmp_path):
        f = _write_par2(tmp_path, [_row(net_sales="$0.00")])
        df = INGESTER.extract_file(f)
        assert df["Net Sales"].iloc[0] == pytest.approx(0.00)

    def test_negative_value_preserved(self, tmp_path):
        f = _write_par2(tmp_path, [_row(net_sales="-$2.50")])
        df = INGESTER.extract_file(f)
        assert df["Net Sales"].iloc[0] == pytest.approx(-2.50)


# ---------------------------------------------------------------------------
# extract_file — metadata columns
# ---------------------------------------------------------------------------


class TestExtractMetadata:
    def test_source_file_set(self, tmp_path):
        f = _write_par2(tmp_path, [_row()], name="DDBB_Apr_25.csv")
        df = INGESTER.extract_file(f)
        assert df["_source_file"].iloc[0] == "DDBB_Apr_25.csv"

    def test_source_system_is_par2(self, tmp_path):
        f = _write_par2(tmp_path, [_row()])
        df = INGESTER.extract_file(f)
        assert df["_source_system"].iloc[0] == "par2"

    def test_ingested_at_present(self, tmp_path):
        f = _write_par2(tmp_path, [_row()])
        df = INGESTER.extract_file(f)
        assert "_ingested_at" in df.columns
        assert df["_ingested_at"].notna().all()


# ---------------------------------------------------------------------------
# extract_file — row handling
# ---------------------------------------------------------------------------


class TestExtractRows:
    def test_empty_csv_returns_empty_df(self, tmp_path):
        f = tmp_path / "DDBB_empty.csv"
        f.write_text(PAR2_HEADER + "\n")
        df = INGESTER.extract_file(f)
        assert df.empty

    def test_multiple_rows_all_returned(self, tmp_path):
        rows = [_row(order_id=f"ORD{i:03d}") for i in range(5)]
        f = _write_par2(tmp_path, rows)
        df = INGESTER.extract_file(f)
        assert len(df) == 5

    def test_voided_rows_not_filtered_by_ingester(self, tmp_path):
        # Voided filtering happens in stg_par2 (dbt), not the ingester
        rows = [_row(voided="True"), _row(voided="False")]
        f = _write_par2(tmp_path, rows)
        df = INGESTER.extract_file(f)
        assert len(df) == 2

    def test_modifier_rows_not_filtered_by_ingester(self, tmp_path):
        # Modifier filtering happens in stg_par2 (dbt), not the ingester
        rows = [_row(is_modifier="True"), _row(is_modifier="False")]
        f = _write_par2(tmp_path, rows)
        df = INGESTER.extract_file(f)
        assert len(df) == 2
