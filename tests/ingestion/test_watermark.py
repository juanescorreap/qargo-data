"""Unit tests for WatermarkManager — engine interactions mocked."""

from unittest.mock import MagicMock, call, patch

import pytest

from ingestion.watermark import WatermarkManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_engine_and_conn():
    """Return (engine mock, conn mock) with the context-manager wiring."""
    engine = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=conn)
    cm.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = cm
    return engine, conn


@pytest.fixture
def wm():
    engine, conn = _make_engine_and_conn()
    with patch.object(WatermarkManager, "_ensure_schema"):
        mgr = WatermarkManager(engine)
    # Keep conn accessible for assertions
    mgr._mock_conn = conn
    mgr._mock_engine = engine
    return mgr


# ---------------------------------------------------------------------------
# _ensure_schema
# ---------------------------------------------------------------------------


class TestEnsureSchema:
    def test_called_on_init(self):
        engine, _ = _make_engine_and_conn()
        with patch.object(WatermarkManager, "_ensure_schema") as mock_ensure:
            WatermarkManager(engine)
        mock_ensure.assert_called_once()

    def test_creates_ingestion_schema(self):
        engine, conn = _make_engine_and_conn()
        WatermarkManager(engine)
        sql_calls = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert any("CREATE SCHEMA IF NOT EXISTS ingestion" in s for s in sql_calls)

    def test_creates_bronze_schema(self):
        engine, conn = _make_engine_and_conn()
        WatermarkManager(engine)
        sql_calls = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert any("CREATE SCHEMA IF NOT EXISTS bronze" in s for s in sql_calls)

    def test_creates_processed_files_table(self):
        engine, conn = _make_engine_and_conn()
        WatermarkManager(engine)
        sql_calls = [str(c.args[0]) for c in conn.execute.call_args_list]
        assert any("processed_files" in s for s in sql_calls)

    def test_commits_after_ddl(self):
        engine, conn = _make_engine_and_conn()
        WatermarkManager(engine)
        conn.commit.assert_called()


# ---------------------------------------------------------------------------
# get_processed
# ---------------------------------------------------------------------------


class TestGetProcessed:
    def test_returns_empty_set_when_no_rows(self, wm):
        engine, conn = _make_engine_and_conn()
        conn.execute.return_value.fetchall.return_value = []
        with patch.object(WatermarkManager, "_ensure_schema"):
            mgr = WatermarkManager(engine)
        result = mgr.get_processed("par2")
        assert result == set()

    def test_returns_set_of_filenames(self, wm):
        engine, conn = _make_engine_and_conn()
        conn.execute.return_value.fetchall.return_value = [
            ("DDBB_Jan_25.csv",),
            ("DDBB_Feb_25.csv",),
        ]
        with patch.object(WatermarkManager, "_ensure_schema"):
            mgr = WatermarkManager(engine)
        result = mgr.get_processed("par2")
        assert result == {"DDBB_Jan_25.csv", "DDBB_Feb_25.csv"}

    def test_single_file(self, wm):
        engine, conn = _make_engine_and_conn()
        conn.execute.return_value.fetchall.return_value = [("DDBB_Mar_25.csv",)]
        with patch.object(WatermarkManager, "_ensure_schema"):
            mgr = WatermarkManager(engine)
        result = mgr.get_processed("par2")
        assert result == {"DDBB_Mar_25.csv"}

    def test_passes_source_name_as_param(self, wm):
        engine, conn = _make_engine_and_conn()
        conn.execute.return_value.fetchall.return_value = []
        with patch.object(WatermarkManager, "_ensure_schema"):
            mgr = WatermarkManager(engine)
        mgr.get_processed("ls2")
        # The second positional arg to execute should contain {"s": "ls2"}
        call_kwargs = conn.execute.call_args
        params = call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs.get("parameters", {})
        assert params.get("s") == "ls2"


# ---------------------------------------------------------------------------
# mark_processed
# ---------------------------------------------------------------------------


class TestMarkProcessed:
    def test_calls_insert_on_conflict(self, wm):
        conn = MagicMock()
        wm.mark_processed(conn, "par2", "DDBB_Jan_25.csv", 100)
        sql_text = str(conn.execute.call_args.args[0])
        assert "INSERT INTO" in sql_text
        assert "ON CONFLICT" in sql_text

    def test_passes_correct_params(self, wm):
        conn = MagicMock()
        wm.mark_processed(conn, "par2", "DDBB_Jan_25.csv", 42)
        params = conn.execute.call_args.args[1]
        assert params["s"] == "par2"
        assert params["f"] == "DDBB_Jan_25.csv"
        assert params["n"] == 42

    def test_references_processed_files_table(self, wm):
        conn = MagicMock()
        wm.mark_processed(conn, "ls2", "file.csv", 0)
        sql_text = str(conn.execute.call_args.args[0])
        assert "processed_files" in sql_text


# ---------------------------------------------------------------------------
# clear_processed
# ---------------------------------------------------------------------------


class TestClearProcessed:
    def test_executes_delete(self, wm):
        conn = MagicMock()
        wm.clear_processed(conn, "par2")
        sql_text = str(conn.execute.call_args.args[0])
        assert "DELETE" in sql_text

    def test_passes_source_name(self, wm):
        conn = MagicMock()
        wm.clear_processed(conn, "ls2")
        params = conn.execute.call_args.args[1]
        assert params["s"] == "ls2"

    def test_different_sources_get_different_params(self, wm):
        conn = MagicMock()
        wm.clear_processed(conn, "par2")
        assert conn.execute.call_args.args[1]["s"] == "par2"

        conn2 = MagicMock()
        wm.clear_processed(conn2, "ls2")
        assert conn2.execute.call_args.args[1]["s"] == "ls2"
