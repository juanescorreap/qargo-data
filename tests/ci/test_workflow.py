"""Structural and syntax tests for .github/workflows/daily_pipeline.yml."""

import ast
import re
import textwrap
from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).parents[2] / ".github" / "workflows" / "daily_pipeline.yml"

EXPECTED_SECRETS = [
    "SUPABASE_DB_URL",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "R2_PUBLIC_URL",
    "PAR_ACCESS_TOKEN",
]

EXPECTED_STEP_NAMES = [
    "Checkout repo",
    "Set up Python 3.12",
    "Install Python dependencies",
    "Run Python tests",
    "Create dbt profiles.yml",
    "Export Supabase connection vars",
    "Load new data into Supabase",
    "Ingest PAR API data",
    "dbt run",
    "dbt test",
    "Install Evidence dependencies",
    "Create Evidence connection.yaml",
    "Generate Evidence sources",
    "Build Evidence dashboard",
    "Configure R2 bucket CORS",
    "Offload large WASM to R2 and patch build",
    "Deploy to Cloudflare Pages",
]

SUPABASE_VARS = [
    "SUPABASE_HOST",
    "SUPABASE_PORT",
    "SUPABASE_DBNAME",
    "SUPABASE_USER",
    "SUPABASE_PASSWORD",
]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text())


@pytest.fixture(scope="module")
def steps(workflow) -> list[dict]:
    return workflow["jobs"]["pipeline"]["steps"]


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW_PATH.read_text()


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------


def _on_block(workflow: dict) -> dict:
    # PyYAML parses the YAML key "on" as the boolean True
    return workflow.get("on") or workflow.get(True, {})


class TestStructure:
    def test_workflow_parses(self, workflow):
        assert workflow is not None

    def test_has_schedule_trigger(self, workflow):
        assert "schedule" in _on_block(workflow)

    def test_has_workflow_dispatch_trigger(self, workflow):
        assert "workflow_dispatch" in _on_block(workflow)

    def test_single_job(self, workflow):
        assert "pipeline" in workflow["jobs"]

    def test_runs_on_ubuntu_latest(self, workflow):
        assert workflow["jobs"]["pipeline"]["runs-on"] == "ubuntu-latest"


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


class TestSteps:
    def test_all_expected_steps_present(self, steps):
        names = [s.get("name", "") for s in steps]
        for expected in EXPECTED_STEP_NAMES:
            assert expected in names, f"Step '{expected}' not found in workflow"

    def test_steps_are_in_correct_order(self, steps):
        names = [s.get("name", "") for s in steps]
        # Every step that exists must appear in the correct relative order
        indices = {n: names.index(n) for n in EXPECTED_STEP_NAMES if n in names}
        ordered = sorted(indices.keys(), key=lambda n: indices[n])
        assert ordered == EXPECTED_STEP_NAMES

    def test_checkout_is_first(self, steps):
        assert steps[0]["name"] == "Checkout repo"

    def test_dbt_run_before_dbt_test(self, steps):
        names = [s.get("name", "") for s in steps]
        assert names.index("dbt run") < names.index("dbt test")

    def test_sources_before_build(self, steps):
        names = [s.get("name", "") for s in steps]
        assert names.index("Generate Evidence sources") < names.index("Build Evidence dashboard")

    def test_r2_offload_before_pages_deploy(self, steps):
        names = [s.get("name", "") for s in steps]
        assert names.index("Offload large WASM to R2 and patch build") < names.index("Deploy to Cloudflare Pages")

    def test_cors_configured_before_offload(self, steps):
        names = [s.get("name", "") for s in steps]
        assert names.index("Configure R2 bucket CORS") < names.index("Offload large WASM to R2 and patch build")


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


class TestSecrets:
    def test_all_required_secrets_referenced(self, workflow_text):
        for secret in EXPECTED_SECRETS:
            assert f"secrets.{secret}" in workflow_text, (
                f"Secret {secret} not referenced in workflow"
            )

    def test_supabase_vars_derived_from_url(self, workflow_text):
        # The "Export Supabase connection vars" step must write these to GITHUB_ENV
        for var in SUPABASE_VARS:
            assert var in workflow_text

    def test_no_vercel_secrets(self, workflow_text):
        assert "VERCEL_TOKEN" not in workflow_text
        assert "VERCEL_ORG_ID" not in workflow_text
        assert "VERCEL_PROJECT_ID" not in workflow_text


# ---------------------------------------------------------------------------
# Cloudflare deploy
# ---------------------------------------------------------------------------


class TestCloudflareDeployStep:
    def _deploy_step(self, steps):
        return next(s for s in steps if s.get("name") == "Deploy to Cloudflare Pages")

    def test_uses_wrangler_3_112(self, steps):
        deploy = self._deploy_step(steps)
        run = deploy.get("run", "")
        assert "wrangler@3.112.0" in run

    def test_no_broken_wrangler_version(self, workflow_text):
        assert "wrangler@3.114.0" not in workflow_text

    def test_deploy_uses_correct_build_dir(self, steps):
        deploy = self._deploy_step(steps)
        run = deploy.get("run", "")
        assert "dashboard/.evidence/template/build" in run

    def test_deploy_targets_qargo_dashboard_project(self, steps):
        deploy = self._deploy_step(steps)
        run = deploy.get("run", "")
        assert "qargo-dashboard" in run

    def test_deploy_has_cloudflare_api_token(self, steps):
        deploy = self._deploy_step(steps)
        env = deploy.get("env", {})
        assert "CLOUDFLARE_API_TOKEN" in env

    def test_deploy_has_cloudflare_account_id(self, steps):
        deploy = self._deploy_step(steps)
        env = deploy.get("env", {})
        assert "CLOUDFLARE_ACCOUNT_ID" in env


# ---------------------------------------------------------------------------
# R2 offload step
# ---------------------------------------------------------------------------


class TestR2OffloadStep:
    def _offload_step(self, steps):
        return next(s for s in steps if s.get("name") == "Offload large WASM to R2 and patch build")

    def test_r2_public_url_in_env(self, steps):
        step = self._offload_step(steps)
        env = step.get("env", {})
        assert "R2_PUBLIC_URL" in env

    def test_calls_ci_r2_offload_script(self, steps):
        step = self._offload_step(steps)
        run = step.get("run", "")
        assert "ci/r2_offload.py" in run


# ---------------------------------------------------------------------------
# Embedded Python syntax validation
# ---------------------------------------------------------------------------


def _extract_inline_python(workflow_text: str) -> list[str]:
    """Return Python code blocks for all << 'PYEOF' heredocs.

    Matches both `python3 - << 'PYEOF'` and `python3 << 'PYEOF'` forms.
    """
    pattern = r"python3\s+(?:-\s+)?<<\s+'PYEOF'\n(.*?)\n\s*PYEOF"
    return re.findall(pattern, workflow_text, re.DOTALL)


class TestEmbeddedPython:
    def test_all_inline_python_scripts_are_valid_syntax(self, workflow_text):
        blocks = _extract_inline_python(workflow_text)
        assert len(blocks) > 0, "Expected at least one inline Python block"
        for code in blocks:
            dedented = textwrap.dedent(code)
            try:
                ast.parse(dedented)
            except SyntaxError as exc:
                pytest.fail(f"Syntax error in embedded Python: {exc}\n\nCode:\n{dedented}")

    def test_profiles_yml_script_uses_supabase_url(self, workflow_text):
        blocks = _extract_inline_python(workflow_text)
        profiles_block = next(
            (b for b in blocks if "profiles" in b and "dbt" in b), None
        )
        assert profiles_block is not None, "Could not find the profiles.yml Python block"
        assert "SUPABASE_DB_URL" in profiles_block

    def test_connection_yaml_script_uses_supabase_vars(self, workflow_text):
        blocks = _extract_inline_python(workflow_text)
        conn_block = next(
            (b for b in blocks if "connection.yaml" in b or "connection" in b), None
        )
        assert conn_block is not None, "Could not find the connection.yaml Python block"
        for var in SUPABASE_VARS:
            assert var in conn_block, f"{var} missing from connection.yaml block"


# ---------------------------------------------------------------------------
# No accidental leftovers
# ---------------------------------------------------------------------------


class TestNoLeftovers:
    def test_no_vercel_deploy_command(self, workflow_text):
        assert "vercel" not in workflow_text.lower()

    def test_no_hardcoded_credentials(self, workflow_text):
        # Passwords must not appear in plain text
        assert "supabase.co" not in workflow_text or "secrets." in workflow_text
        # All DB-related values should come from secrets
        lines_with_pooler = [
            ln for ln in workflow_text.splitlines()
            if "pooler.supabase.com" in ln
        ]
        assert all("secrets." in ln for ln in lines_with_pooler)

    def test_node24_flag_set(self, workflow):
        assert workflow.get("env", {}).get("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24") is True
