"""Unit tests for FileBasedLoader — all DB operations mocked."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from ingestion.loader import FileBasedLoader


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_engine(table_exists: bool = False):
    """Return (engine, conn) mock pair.

    conn.execute(...).scalar() returns *table_exists* — used for the
    `SELECT EXISTS(...)` check in FileBasedLoader.load().
    """
    engine = MagicMock()
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = table_exists
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=conn)
    cm.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = cm
    return engine, conn


def _make_ingester(
    source_name="par2",
    target_table="raw_par2",
    date_column="Date",
    files: list[Path] | None = None,
    df: pd.DataFrame | None = None,
):
    ingester = MagicMock()
    ingester.source_name = source_name
    ingester.target_table = target_table
    ingester.date_column = date_column
    ingester.list_files.return_value = files or []
    ingester.extract_file.return_value = df if df is not None else pd.DataFrame()
    return ingester


def _sample_df(n: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        "Date": [date(2025, 1, i + 1) for i in range(n)],
        "Net Sales": [float(i + 1) for i in range(n)],
        "Order ID": [f"ORD{i:03d}" for i in range(n)],
    })


# ---------------------------------------------------------------------------
# load() — no files
# ---------------------------------------------------------------------------


class TestLoadNoFiles:
    @patch("ingestion.loader.WatermarkManager")
    def test_returns_zero_when_no_files(self, MockWM, tmp_path):
        engine, _ = _make_engine()
        MockWM.return_value.get_processed.return_value = set()
        ingester = _make_ingester(files=[])

        loader = FileBasedLoader(engine, tmp_path)
        assert loader.load(ingester) == 0

    @patch("ingestion.loader.WatermarkManager")
    def test_calls_list_files_with_data_dir(self, MockWM, tmp_path):
        engine, _ = _make_engine()
        MockWM.return_value.get_processed.return_value = set()
        ingester = _make_ingester(files=[])

        loader = FileBasedLoader(engine, tmp_path)
        loader.load(ingester)
        ingester.list_files.assert_called_once_with(tmp_path)


# ---------------------------------------------------------------------------
# load() — all files already processed (watermark)
# ---------------------------------------------------------------------------


class TestLoadAllProcessed:
    @patch("ingestion.loader.WatermarkManager")
    def test_returns_zero_when_all_processed(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, _ = _make_engine()
        MockWM.return_value.get_processed.return_value = {"DDBB_Jan_25.csv"}
        ingester = _make_ingester(files=[csv], df=_sample_df())

        loader = FileBasedLoader(engine, tmp_path)
        assert loader.load(ingester) == 0

    @patch("ingestion.loader.WatermarkManager")
    def test_does_not_call_extract_when_all_processed(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, _ = _make_engine()
        MockWM.return_value.get_processed.return_value = {"DDBB_Jan_25.csv"}
        ingester = _make_ingester(files=[csv], df=_sample_df())

        loader = FileBasedLoader(engine, tmp_path)
        loader.load(ingester)
        ingester.extract_file.assert_not_called()

    @patch("ingestion.loader.WatermarkManager")
    def test_processes_only_new_files(self, MockWM, tmp_path):
        old = tmp_path / "DDBB_Jan_25.csv"
        new = tmp_path / "DDBB_Feb_25.csv"
        old.touch()
        new.touch()
        engine, _ = _make_engine()
        MockWM.return_value.get_processed.return_value = {"DDBB_Jan_25.csv"}
        ingester = _make_ingester(files=[old, new], df=_sample_df(2))

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            loader.load(ingester)

        ingester.extract_file.assert_called_once_with(new)


# ---------------------------------------------------------------------------
# load() — empty DataFrame
# ---------------------------------------------------------------------------


class TestLoadEmptyDataFrame:
    @patch("ingestion.loader.WatermarkManager")
    def test_returns_zero_on_empty_df(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, _ = _make_engine()
        MockWM.return_value.get_processed.return_value = set()
        ingester = _make_ingester(files=[csv], df=pd.DataFrame())

        loader = FileBasedLoader(engine, tmp_path)
        assert loader.load(ingester) == 0

    @patch("ingestion.loader.WatermarkManager")
    def test_does_not_mark_empty_file_as_processed(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, _ = _make_engine()
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        ingester = _make_ingester(files=[csv], df=pd.DataFrame())

        loader = FileBasedLoader(engine, tmp_path)
        loader.load(ingester)
        mock_wm.mark_processed.assert_not_called()


# ---------------------------------------------------------------------------
# load() — new table (first insert)
# ---------------------------------------------------------------------------


class TestLoadNewTable:
    @patch("ingestion.loader.WatermarkManager")
    def test_to_sql_called_with_replace_when_table_new(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, conn = _make_engine(table_exists=False)
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        df = _sample_df()
        ingester = _make_ingester(files=[csv], df=df)

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql") as mock_to_sql:
            loader.load(ingester)

        mock_to_sql.assert_called_once()
        _, kwargs = mock_to_sql.call_args
        assert kwargs["if_exists"] == "replace"
        assert kwargs["schema"] == "bronze"

    @patch("ingestion.loader.WatermarkManager")
    def test_no_delete_when_table_is_new(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, conn = _make_engine(table_exists=False)
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        ingester = _make_ingester(files=[csv], df=_sample_df())

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            loader.load(ingester)

        executed_sql = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert not any("DELETE" in s for s in executed_sql)


# ---------------------------------------------------------------------------
# load() — existing table (append path)
# ---------------------------------------------------------------------------


class TestLoadExistingTable:
    @patch("ingestion.loader.WatermarkManager")
    def test_to_sql_called_with_append_when_table_exists(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, _ = _make_engine(table_exists=True)
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        ingester = _make_ingester(files=[csv], df=_sample_df())

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql") as mock_to_sql:
            loader.load(ingester)

        _, kwargs = mock_to_sql.call_args
        assert kwargs["if_exists"] == "append"

    @patch("ingestion.loader.WatermarkManager")
    def test_deletes_date_range_before_insert_when_table_exists(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, conn = _make_engine(table_exists=True)
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        ingester = _make_ingester(files=[csv], df=_sample_df())

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            loader.load(ingester)

        executed_sql = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert any("DELETE" in s for s in executed_sql)

    @patch("ingestion.loader.WatermarkManager")
    def test_delete_uses_date_range_from_df(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, conn = _make_engine(table_exists=True)
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        df = pd.DataFrame({"Date": [date(2025, 1, 1), date(2025, 1, 31)], "Net Sales": [1.0, 2.0], "Order ID": ["A", "B"]})
        ingester = _make_ingester(files=[csv], df=df)

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            loader.load(ingester)

        delete_calls = [c for c in conn.execute.call_args_list if "DELETE" in str(c.args[0])]
        assert len(delete_calls) == 1
        params = delete_calls[0].args[1]
        assert params["min_d"] == date(2025, 1, 1)
        assert params["max_d"] == date(2025, 1, 31)


# ---------------------------------------------------------------------------
# load() — post-insert steps
# ---------------------------------------------------------------------------


class TestLoadPostInsert:
    @patch("ingestion.loader.WatermarkManager")
    def test_creates_date_index_after_insert(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, conn = _make_engine()
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        ingester = _make_ingester(files=[csv], df=_sample_df())

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            loader.load(ingester)

        sql_calls = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert any("CREATE INDEX" in s for s in sql_calls)

    @patch("ingestion.loader.WatermarkManager")
    def test_marks_file_processed_after_insert(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, conn = _make_engine()
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        df = _sample_df(5)
        ingester = _make_ingester(files=[csv], df=df)

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            loader.load(ingester)

        mock_wm.mark_processed.assert_called_once_with(
            conn, "par2", "DDBB_Jan_25.csv", 5
        )

    @patch("ingestion.loader.WatermarkManager")
    def test_returns_total_row_count(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, _ = _make_engine()
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        ingester = _make_ingester(files=[csv], df=_sample_df(7))

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            result = loader.load(ingester)

        assert result == 7


# ---------------------------------------------------------------------------
# load() — full_refresh
# ---------------------------------------------------------------------------


class TestLoadFullRefresh:
    @patch("ingestion.loader.WatermarkManager")
    def test_full_refresh_processes_all_files_ignoring_watermark(self, MockWM, tmp_path):
        csv1 = tmp_path / "DDBB_Jan_25.csv"
        csv2 = tmp_path / "DDBB_Feb_25.csv"
        csv1.touch()
        csv2.touch()
        engine, _ = _make_engine()
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        # Both already in watermark — should still be processed
        mock_wm.get_processed.return_value = {"DDBB_Jan_25.csv", "DDBB_Feb_25.csv"}
        ingester = _make_ingester(files=[csv1, csv2], df=_sample_df(2))

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            loader.load(ingester, full_refresh=True)

        assert ingester.extract_file.call_count == 2

    @patch("ingestion.loader.WatermarkManager")
    def test_full_refresh_clears_watermark(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, conn = _make_engine()
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        ingester = _make_ingester(files=[csv], df=_sample_df())

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            loader.load(ingester, full_refresh=True)

        mock_wm.clear_processed.assert_called_once_with(conn, "par2")

    @patch("ingestion.loader.WatermarkManager")
    def test_full_refresh_drops_bronze_table(self, MockWM, tmp_path):
        csv = tmp_path / "DDBB_Jan_25.csv"
        csv.touch()
        engine, conn = _make_engine()
        mock_wm = MagicMock()
        MockWM.return_value = mock_wm
        mock_wm.get_processed.return_value = set()
        ingester = _make_ingester(files=[csv], df=_sample_df())

        loader = FileBasedLoader(engine, tmp_path)
        with patch.object(pd.DataFrame, "to_sql"):
            loader.load(ingester, full_refresh=True)

        sql_calls = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert any("DROP TABLE" in s for s in sql_calls)
