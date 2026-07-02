# Security Forensics Report — Credential Exposure Diagnosis

> **Phase:** READ-ONLY forensic assessment. No remediation performed. No credentials rotated. No files modified or deleted except creation of this report. No `git add`/`commit`/history rewrite executed.
> **Date:** 2026-06-25
> **Repo:** `juanescorreap/qargo-data` · branch `main` @ `f0b01c8` (up to date with `origin/main`)

---

## Executive Summary (5 lines)

1. **A live plaintext Supabase password + full connection string sits in the UNCOMMITTED working tree** of `dashboard/sources/gold/connection.yaml`, replacing the `${SUPABASE_*}` env-var placeholders — **CRITICAL**, imminent leak if committed/pushed.
2. **Good news:** the committed history of that file **never** contained the real password — all 6 historical commits used `${SUPABASE_*}` placeholders only. The password value is **not** in any commit and **not** on the remote.
3. **Bad news:** committed file `logs/dbt.log` (tracked in HEAD, present across ~all commits) **publicly exposes the DB host, user, port and database name** (no password) — **HIGH**, because the repo is **PUBLIC**.
4. **The GitHub repo is PUBLIC** (`visibility: PUBLIC`) — any secret reaching its history must be treated as compromised; partial DB credentials already are.
5. **C6 confirmed:** `verify=False` exists in exactly one place (`ingestion/par_api.py:70`, the PAR client); plus `rejectUnauthorized: false` in DB connection configs — TLS validation disabled, MITM-exploitable.

**Overall posture: CRITICAL** — driven by public-repo visibility + an about-to-be-committed plaintext password + already-public partial DB credentials + disabled TLS.

---

## 1. Working Tree State

**`git status`** — branch `main`, up to date with `origin/main`. One modified tracked file:
- `dashboard/sources/gold/connection.yaml` (modified, **not staged**)
- Untracked: `AUDIT.md`, `SECURITY_FORENSICS_REPORT.md` (this file), `scripts/`, several `*.xlsx`/`.csv`.

**`git diff -- dashboard/sources/gold/connection.yaml`** — the uncommitted change **replaces env-var placeholders with hardcoded real values**:

| Line (new) | Field | Contains secret? | Value (redacted) |
|---|---|---|---|
| `+database: postgres` | database | No | `postgres` |
| `+host: aws-1-us-east-1.pooler.supabase.com` | host | Partial cred | `aws-1-us-east-1.pooler.supabase.com` |
| `+password: …` | **password** | **YES — plaintext password** | `password: REDACTED_PLAINTEXT_SECRET_FOUND` |
| `+port: 6543` | port | No | `6543` |
| `+user: postgres.ylos…REDACTED` | user (project ref) | Partial cred | `postgres.<project_ref>` |

Removed lines were the safe `${SUPABASE_HOST/PORT/DBNAME/USER/PASSWORD}` placeholders.

> **Finding 1.1 — CRITICAL.** Live plaintext Supabase **password** present in working tree at `dashboard/sources/gold/connection.yaml` (the `password:` line). Currently local only (not committed, not pushed). If committed to this **public** repo it is instantly compromised. Confirmed independently by `detect-secrets` (§3).

---

## 2. History of the Specific File

`git log -p --follow -- dashboard/sources/gold/connection.yaml` — 6 commits touch the file, all by `juanescorreap <juanestebancope@outlook.com>` on 2026-05-26:

| Commit | Date | Author | Secret in committed diff? | Type |
|---|---|---|---|---|
| `c0fde0d` | 2026-05-26 | juanescorreap | No | placeholder `${SUPABASE_HOST}` |
| `94b43f3` | 2026-05-26 | juanescorreap | No | placeholders `${SUPABASE_USER/PASSWORD}` |
| `ba29d21` | 2026-05-26 | juanescorreap | No | placeholders only |
| `3ab30da` | 2026-05-26 | juanescorreap | No | placeholders only |
| `9ed426b` | 2026-05-26 | juanescorreap | No | placeholders only |
| `01e4c69` | 2026-05-26 | juanescorreap | No | initial, placeholders |

> **Finding 2.1 — INFO / GOOD.** The **committed** history of `connection.yaml` never exposed the real password or any literal credential — only `${SUPABASE_*}` env references. The plaintext secret exists **only** in the current uncommitted working tree (§1).

---

## 3. Full-History Scan (entire repo, all commits)

**Tooling:** no `gitleaks` / `trufflehog` installed. Installed `detect-secrets` via pip (`~/.local/bin/detect-secrets`) — no project files modified. History coverage cross-checked with `git grep` over **all 53 commits** (`git rev-list --all`).

**3a. `detect-secrets scan` (working tree, tracked dirs):** 1 finding —
`dashboard/sources/gold/connection.yaml` → `Secret Keyword` (the uncommitted password, Finding 1.1).

**3b. Known-value grep across ALL commits (`git grep <value> $(git rev-list --all)`):**

| Indicator | In history? | Where | Still in HEAD? |
|---|---|---|---|
| Password value `s7p…REDACTED` | **No** — zero matches in any commit | — | No (working tree only) |
| Host `…pooler.supabase.com` | **Yes** — present in ~all commits | `logs/dbt.log:233`, `tests/ci/test_workflow.py:276` | **Yes** |
| User / project-ref `postgres.ylos…` | **Yes** — present in ~all commits | `logs/dbt.log:235` | **Yes** |

> **Finding 3.1 — HIGH.** `logs/dbt.log` is **committed and tracked in HEAD**, leaking DB **host + user + port + database** (no password) in plaintext across the repo history. `git show HEAD:logs/dbt.log` confirms the `Connection:` block. In a **public** repo this is live partial-credential exposure (everything but the password). A build/log artifact should never be committed.
>
> **Finding 3.2 — INFO.** `tests/ci/test_workflow.py:276` contains the literal `"pooler.supabase.com"` — but inside `test_no_hardcoded_credentials`, an **assertion** that the workflow has no hardcoded host. Benign by intent; still places the host substring in public source.
>
> **Finding 3.3 — GOOD.** The actual password value is **absent from the entire git history** — it was never committed or pushed. Remote remediation for the password is therefore *preventive* (don't commit it), not *historical* (no purge needed for the password specifically).

---

## 4. Visibility & Exposure Surface

- **`git remote -v`:** `origin → https://github.com/juanescorreap/qargo-data.git` (fetch + push).
- **`gh repo view --json visibility,isPrivate`:** `{"isPrivate": false, "visibility": "PUBLIC"}`.

> **Finding 4.1 — CRITICAL (amplifier).** The repository is **PUBLIC on GitHub**. Anything in its history is world-readable and likely already crawled/cached. The partial DB credentials in `logs/dbt.log` (Finding 3.1) **must be treated as already compromised**. The Supabase pooler host + project ref + username are public; only the password gates access — and that password is the value sitting one `git commit` away in the working tree (Finding 1.1).

---

## 5. C6 Validation — TLS `verify=False` / disabled verification

| File:Line | Context | Type |
|---|---|---|
| `ingestion/par_api.py:70` | `async with httpx.AsyncClient(verify=False) as client:` — PAR POS SOAP client | **TLS verification OFF on HTTP client** |
| `dashboard/sources/gold/connection.yaml:8` | `ssl: rejectUnauthorized: false` | Postgres TLS not validated (Evidence) |
| `dashboard/.evidence/template/sources/gold/connection.yaml:8` | `ssl: rejectUnauthorized: false` | same, template copy |
| `.github/workflows/daily_pipeline.yml:138` | `'ssl': {'rejectUnauthorized': False}` | Postgres TLS not validated (CI-generated config) |

- **No `verify_ssl` parametrization** found anywhere.
- **No centralized `BaseClient`** — `ingestion/par_api.py` is the **only** HTTP client and configures `verify=False` inline.

> **Finding 5.1 — HIGH.** `ingestion/par_api.py:70` disables TLS verification while sending `AccessToken` + `LocationToken` in headers → MITM can intercept POS credentials. **Single location** → Phase-2 fix is a **one-line change** (`verify=True` + correct CA bundle).
>
> **Finding 5.2 — MEDIUM.** `rejectUnauthorized: false` disables Postgres TLS certificate validation in **3 spots** (2 connection.yaml + CI workflow generator). Fix touches multiple files; the `.evidence/template/` copy and the CI generator must be fixed together or the value regenerates.

---

## 6. Other Secrets Outside connection.yaml

- **Hardcoded `password|api_key|secret|token = "…"` grep** (py/yaml/yml/env): **no matches** beyond the connection.yaml finding already reported. The YAML password is unquoted so it surfaced via §1/§3, not this quoted-string pattern.
- **`.env` tracked by git?** `git ls-files | grep -i env` → **`.env` is NOT tracked.** A `.env` exists on disk locally but is correctly excluded from git.

> **Finding 6.1 — GOOD.** No additional hardcoded secrets in tracked source. `.env` is untracked (correctly gitignored). The only credential-bearing artifacts in git are the uncommitted `connection.yaml` (§1) and the committed `logs/dbt.log` (§3).
>
> **Finding 6.2 — INFO.** A full `detect-secrets scan --all-files` flags `.env` (`Basic Auth Credentials`, `Secret Keyword`) — it holds live secrets **on disk**, but is **not git-tracked**, so no repository exposure. All other hits (`.venv/`, `.pytest_cache/`) are third-party library false-positives and are not git-tracked. No additional git-exposed secret found.

---

## Findings Summary (by severity)

| ID | Severity | Finding | Location |
|---|---|---|---|
| 1.1 | **CRITICAL** | Plaintext Supabase password in uncommitted working tree (about to be committed to a public repo) | `dashboard/sources/gold/connection.yaml` (uncommitted) |
| 4.1 | **CRITICAL** | Repo is PUBLIC → any history secret = compromised; partial DB creds already public | GitHub `juanescorreap/qargo-data` |
| 3.1 | **HIGH** | DB host + user + port + database committed & live in HEAD (public) | `logs/dbt.log` |
| 5.1 | **HIGH** | `verify=False` on PAR client sending auth tokens → MITM (single location) | `ingestion/par_api.py:70` |
| 5.2 | **MEDIUM** | Postgres TLS validation disabled (`rejectUnauthorized: false`), 3 spots | connection.yaml ×2, `daily_pipeline.yml:138` |
| 3.2 | **LOW/INFO** | Host literal in a test assertion (benign intent) | `tests/ci/test_workflow.py:276` |
| 2.1 | **INFO/GOOD** | Committed history of connection.yaml never held real password | — |
| 3.3 | **INFO/GOOD** | Password value absent from entire git history (never pushed) | — |
| 6.1 | **INFO/GOOD** | `.env` untracked; no other hardcoded secrets | — |

## Note on Scope (for the remediation phase — NOT performed here)

- Password remediation is **preventive** (the value never hit history/remote) — but because the repo is public and the password is the only gate over already-public host/user, treat it as **high urgency** regardless.
- `logs/dbt.log` exposure **is** historical (in HEAD and prior commits on a public remote) — would require history purge + treating host/user/project-ref as disclosed.
- No credentials were rotated, no files altered, no commits made. This report is the sole artifact created.
