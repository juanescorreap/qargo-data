"""
On-demand security regression check — incident 2026-06-25.

Asserts the Supabase database password that was EXPOSED in the incident can no
longer authenticate (i.e. the rotation has not regressed).

This test is INERT by default: it is skipped unless the leaked password is provided
explicitly via the LEAKED_PG_PASSWORD environment variable. It must NOT be wired into
the daily production pipeline — it is a manual, on-demand check.

The leaked value is NEVER hardcoded here or committed. Supply it ephemerally:

    LEAKED_PG_PASSWORD='<old-exposed-password>' \
    SUPABASE_HOST=... SUPABASE_PORT=... SUPABASE_DBNAME=... SUPABASE_USER=... \
    pytest tests/security/test_leaked_credential_revoked.py -v

(or `set -a && source .env && set +a` first to load host/port/dbname/user, then prepend
LEAKED_PG_PASSWORD inline). The leaked value is read only from the environment and is
never printed.
"""
from __future__ import annotations

import os

import psycopg2
import pytest

LEAKED = os.environ.get("LEAKED_PG_PASSWORD")


@pytest.mark.skipif(
    not LEAKED,
    reason="LEAKED_PG_PASSWORD not set — on-demand check, inert by default.",
)
def test_leaked_credential_is_revoked():
    conn_kwargs = dict(
        host=os.environ["SUPABASE_HOST"],
        port=int(os.environ.get("SUPABASE_PORT", "6543")),
        dbname=os.environ.get("SUPABASE_DBNAME", "postgres"),
        user=os.environ["SUPABASE_USER"],
        password=LEAKED,
        sslmode="require",
        connect_timeout=10,
    )

    try:
        conn = psycopg2.connect(**conn_kwargs)
    except psycopg2.OperationalError as exc:
        msg = str(exc).lower()
        if "authentication failed" in msg or "password" in msg:
            # Expected, healthy outcome: the leaked password is rejected.
            return
        # Network/TLS/other failure — cannot conclude the credential is dead.
        pytest.skip(f"Inconclusive (non-auth connection error): {type(exc).__name__}")
    else:
        conn.close()
        pytest.fail(
            "CRITICAL: leaked credential from incident 2026-06-25 is still valid — "
            "rotation has regressed."
        )
