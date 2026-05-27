"""Unit tests for ci/r2_offload.py — subprocess mocked, filesystem real (tmp_path)."""

from pathlib import Path
from unittest.mock import call, patch

import pytest

from ci.r2_offload import PAGES_LIMIT_BYTES, offload

R2_BASE = "https://pub-abc123.r2.dev"
BUCKET = "qargo-assets"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wasm(path: Path, size_bytes: int) -> Path:
    """Create a dummy file of exactly *size_bytes*."""
    path.write_bytes(b"\x00" * size_bytes)
    return path


def _build_dir(tmp_path: Path) -> Path:
    d = tmp_path / "build"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Files within the 25 MiB limit
# ---------------------------------------------------------------------------


class TestSmallWasm:
    @patch("ci.r2_offload.subprocess.run")
    def test_small_wasm_not_uploaded(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "duckdb-mvp.wasm", PAGES_LIMIT_BYTES - 1)

        offload(bd, R2_BASE, BUCKET)
        mock_run.assert_not_called()

    @patch("ci.r2_offload.subprocess.run")
    def test_small_wasm_not_deleted(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        wasm = _make_wasm(bd / "duckdb-mvp.wasm", PAGES_LIMIT_BYTES - 1)

        offload(bd, R2_BASE, BUCKET)
        assert wasm.exists()

    @patch("ci.r2_offload.subprocess.run")
    def test_exactly_at_limit_not_offloaded(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "edge.wasm", PAGES_LIMIT_BYTES)

        offload(bd, R2_BASE, BUCKET)
        mock_run.assert_not_called()

    @patch("ci.r2_offload.subprocess.run")
    def test_small_wasm_not_in_offloaded_list(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "small.wasm", 1024)

        result = offload(bd, R2_BASE, BUCKET)
        assert result == []


# ---------------------------------------------------------------------------
# Files exceeding the 25 MiB limit
# ---------------------------------------------------------------------------


class TestLargeWasm:
    @patch("ci.r2_offload.subprocess.run")
    def test_large_wasm_triggers_upload(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        assets = bd / "_app" / "immutable" / "assets"
        assets.mkdir(parents=True)
        _make_wasm(assets / "duckdb-eh.abc123.wasm", PAGES_LIMIT_BYTES + 1)

        offload(bd, R2_BASE, BUCKET)
        mock_run.assert_called_once()

    @patch("ci.r2_offload.subprocess.run")
    def test_upload_uses_wrangler_3_112(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "big.wasm", PAGES_LIMIT_BYTES + 1)

        offload(bd, R2_BASE, BUCKET)
        cmd = mock_run.call_args.args[0]
        assert "wrangler@3.112.0" in cmd

    @patch("ci.r2_offload.subprocess.run")
    def test_upload_command_is_r2_object_put(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "big.wasm", PAGES_LIMIT_BYTES + 1)

        offload(bd, R2_BASE, BUCKET)
        cmd = mock_run.call_args.args[0]
        assert "r2" in cmd
        assert "object" in cmd
        assert "put" in cmd

    @patch("ci.r2_offload.subprocess.run")
    def test_r2_key_is_flat_filename(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        assets = bd / "_app" / "immutable" / "assets"
        assets.mkdir(parents=True)
        wasm_name = "duckdb-eh.abc123.wasm"
        _make_wasm(assets / wasm_name, PAGES_LIMIT_BYTES + 1)

        offload(bd, R2_BASE, BUCKET)
        cmd = mock_run.call_args.args[0]
        # R2 key should be "qargo-assets/duckdb-eh.abc123.wasm", not include the subpath
        r2_object_arg = next(a for a in cmd if a.startswith(f"{BUCKET}/"))
        assert r2_object_arg == f"{BUCKET}/{wasm_name}"

    @patch("ci.r2_offload.subprocess.run")
    def test_content_type_is_application_wasm(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "big.wasm", PAGES_LIMIT_BYTES + 1)

        offload(bd, R2_BASE, BUCKET)
        cmd = mock_run.call_args.args[0]
        assert "--content-type" in cmd
        idx = cmd.index("--content-type")
        assert cmd[idx + 1] == "application/wasm"

    @patch("ci.r2_offload.subprocess.run")
    def test_check_true_propagates_wrangler_failure(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "big.wasm", PAGES_LIMIT_BYTES + 1)

        offload(bd, R2_BASE, BUCKET)
        assert mock_run.call_args.kwargs.get("check") is True

    @patch("ci.r2_offload.subprocess.run")
    def test_large_wasm_deleted_after_upload(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        wasm = _make_wasm(bd / "big.wasm", PAGES_LIMIT_BYTES + 1)

        offload(bd, R2_BASE, BUCKET)
        assert not wasm.exists()

    @patch("ci.r2_offload.subprocess.run")
    def test_large_wasm_appears_in_offloaded_list(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "duckdb-eh.xyz.wasm", PAGES_LIMIT_BYTES + 1)

        result = offload(bd, R2_BASE, BUCKET)
        assert result == ["duckdb-eh.xyz.wasm"]

    @patch("ci.r2_offload.subprocess.run")
    def test_multiple_large_wasm_all_offloaded(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "a.wasm", PAGES_LIMIT_BYTES + 1)
        _make_wasm(bd / "b.wasm", PAGES_LIMIT_BYTES + 1)

        result = offload(bd, R2_BASE, BUCKET)
        assert set(result) == {"a.wasm", "b.wasm"}
        assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# JS patching
# ---------------------------------------------------------------------------


class TestJsPatching:
    @patch("ci.r2_offload.subprocess.run")
    def test_js_file_with_matching_path_is_patched(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        assets = bd / "_app" / "immutable" / "assets"
        assets.mkdir(parents=True)
        wasm_name = "duckdb-eh.hash.wasm"
        _make_wasm(assets / wasm_name, PAGES_LIMIT_BYTES + 1)

        rel_path = f"/_app/immutable/assets/{wasm_name}"
        expected_r2_url = f"{R2_BASE}/{wasm_name}"
        js = bd / "chunk.js"
        js.write_text(f'const url="{rel_path}";', "utf-8")

        offload(bd, R2_BASE, BUCKET)
        assert expected_r2_url in js.read_text("utf-8")

    @patch("ci.r2_offload.subprocess.run")
    def test_js_without_matching_path_untouched(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "big.wasm", PAGES_LIMIT_BYTES + 1)

        original_content = 'const msg = "hello world";'
        js = bd / "other.js"
        js.write_text(original_content, "utf-8")

        offload(bd, R2_BASE, BUCKET)
        assert js.read_text("utf-8") == original_content

    @patch("ci.r2_offload.subprocess.run")
    def test_rel_path_is_slash_prefixed(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        sub = bd / "assets"
        sub.mkdir()
        wasm_name = "big.wasm"
        _make_wasm(sub / wasm_name, PAGES_LIMIT_BYTES + 1)

        js = bd / "app.js"
        # rel_path should be /assets/big.wasm (leading slash, forward slashes)
        js.write_text(f'"{"/assets/" + wasm_name}"', "utf-8")

        offload(bd, R2_BASE, BUCKET)
        assert R2_BASE in js.read_text("utf-8")

    @patch("ci.r2_offload.subprocess.run")
    def test_r2_url_uses_r2_base_and_filename(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        wasm_name = "duckdb-eh.wasm"
        _make_wasm(bd / wasm_name, PAGES_LIMIT_BYTES + 1)

        js = bd / "app.js"
        js.write_text(f'"/{wasm_name}"', "utf-8")

        offload(bd, R2_BASE, BUCKET)
        expected_url = f"{R2_BASE}/{wasm_name}"
        assert expected_url in js.read_text("utf-8")

    @patch("ci.r2_offload.subprocess.run")
    def test_r2_base_trailing_slash_stripped(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        wasm_name = "big.wasm"
        _make_wasm(bd / wasm_name, PAGES_LIMIT_BYTES + 1)
        js = bd / "app.js"
        js.write_text(f'"/{wasm_name}"', "utf-8")

        offload(bd, f"{R2_BASE}/", BUCKET)  # trailing slash
        content = js.read_text("utf-8")
        # Should not have double slashes
        assert "r2.dev//" not in content


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @patch("ci.r2_offload.subprocess.run")
    def test_empty_build_dir_returns_empty_list(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        result = offload(bd, R2_BASE, BUCKET)
        assert result == []
        mock_run.assert_not_called()

    @patch("ci.r2_offload.subprocess.run")
    def test_no_wasm_files_at_all(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        (bd / "app.js").write_text("// nothing here", "utf-8")
        (bd / "style.css").write_text("body{}", "utf-8")

        result = offload(bd, R2_BASE, BUCKET)
        assert result == []

    @patch("ci.r2_offload.subprocess.run")
    def test_mixed_small_and_large_wasm(self, mock_run, tmp_path):
        bd = _build_dir(tmp_path)
        _make_wasm(bd / "small.wasm", 1024)
        small = bd / "small.wasm"
        large = _make_wasm(bd / "large.wasm", PAGES_LIMIT_BYTES + 1)

        result = offload(bd, R2_BASE, BUCKET)
        assert result == ["large.wasm"]
        assert small.exists()      # small kept
        assert not large.exists()  # large removed
        mock_run.assert_called_once()
