# AGENTS.md

## Repository Overview

- `pluse-board` is a private health dashboard: Google Health API -> BigQuery -> SQLMesh -> Evidence -> GitHub Pages.
- The spelling `pluse` is intentional: it combines "plus" and "pulse".
- Treat health data, OAuth credentials, GCP settings, and GitHub secrets as sensitive.

## Working Rules

- Do not push directly to `main`. Use a pull request unless the user explicitly asks for a direct push.
- Keep changes narrowly scoped. Avoid unrelated refactors, lockfile churn, or generated artifact updates.
- Preserve user work in the tree. There may be unrelated modified or untracked files; do not revert, delete, or stage them unless asked.
- Do not commit local credentials, profiles, cache files, build output, or downloaded data.
- Do not change GitHub repository settings, branch protection, GCP IAM, Workload Identity Federation, GitHub Secrets, or GitHub Variables unless the user explicitly asks.

## Verification

Run the smallest relevant checks for the files changed.

- GitHub Actions workflows: `./scripts/actionlint`
- Python dependency metadata: `UV_CACHE_DIR=.uv-cache uv lock --check`
- Python dependency install check: `uv sync --frozen --only-group ingest` and/or `uv sync --frozen --only-group sqlmesh`
- Evidence dependency install check: `cd reports && npm ci`
- Evidence build check, when report pages or sources change and BigQuery credentials are available: `cd reports && npm run sources && npm run build`
- SQLMesh check, when models change and BigQuery + state credentials are available: `uv sync --only-group sqlmesh && cd sqlmesh_project && uv run sqlmesh plan dev`

If a check cannot run because it needs external credentials, network access, Docker daemon access, or GCP access, say that clearly and run the closest local/static check instead.

## CI and Dependabot

- Required PR checks are expected to include:
  - `PR Check / GitHub Actions lint`
  - `PR Check / Python lock`
  - `PR Check / Reports lock`
- Dependabot manages:
  - root `uv` dependencies
  - `reports/` npm dependencies
  - GitHub Actions versions
- Dependabot patch and minor PRs may be auto-merged only after required checks pass.
- Major dependency updates should remain manual review items.
- Do not broaden Dependabot scope to untracked or experimental manifests without user confirmation.

## Automation Boundaries

For scheduled or background agents:

- If Daily Build fails due to an obvious code, workflow, lockfile, SQLMesh, or report issue, it is acceptable to propose or prepare a minimal PR.
- If the failure appears related to Health API availability, token refresh, BigQuery data freshness, GCP IAM, WIF, GitHub Pages settings, GitHub Secrets, or GitHub Variables, do not attempt an automatic fix. Report the likely cause and the manual action needed.
- Never rotate secrets, alter IAM, change repository security settings, or bypass branch protection from automation.

## Issue Tracking

This project uses **bd (beads)** for issue tracking. Run `bd prime` for full workflow context.

- `bd ready` — find unblocked work
- `bd create "Title" -t task -p 2` — create issue (types: bug/feature/task/epic/chore; priorities 0-4)
- `bd update <id> --claim` — claim work atomically
- `bd close <id>` — mark complete
- `bd list --status=open` / `bd search "text"` — list / search issues

Use `bd` for ALL task tracking in this project — do NOT use TodoWrite, TaskCreate, or markdown TODO lists.

**Sync:** the source of truth is the DoltHub remote for this repo.
- `bd dolt pull` — sync latest before starting work
- `bd dolt push` — sync your changes back at end of session
- Do not hand-edit `.beads/issues.jsonl`; use `bd` commands.

## Cursor Cloud specific instructions

The VM startup update script installs `uv`, runs `uv sync --frozen` (groups `ingest`,
`dev`, `sqlmesh`, `lineage`), and `npm --prefix reports ci`. `uv` lives at
`~/.local/bin` and is on `PATH` in login shells (`~/.bashrc` sources `~/.local/bin/env`);
non-login shells may need `export PATH="$HOME/.local/bin:$PATH"` first.

What runs offline (no GCP/BigQuery/OAuth/Neon — the common case in cloud):
- Python tests: `uv run pytest --cov` (external services are mocked; see `tests/`).
- Lint/lock checks per the `## Verification` section (`./scripts/actionlint`,
  `UV_CACHE_DIR=.uv-cache uv lock --check`). `actionlint` self-pins via the Go
  toolchain when no local binary/Docker exists; first run downloads Go modules.

What needs secrets (cannot run in a credential-less VM):
- `ingest/pull_health_api.py` (Google Health OAuth + BigQuery write).
- Evidence `npm run sources` and SQLMesh `plan/run` (both need BigQuery auth;
  prod/`ci` SQLMesh also needs Neon Postgres state).

Demonstrating the Evidence dashboard app WITHOUT BigQuery credentials: the pages
query a source named `bq`. Temporarily point it at a local DuckDB seed instead of
BigQuery — install the connector with `npm --prefix reports install --no-save
@evidence-dev/duckdb`, add `"@evidence-dev/duckdb": {}` under `plugins.datasources`
in `reports/evidence.config.yaml`, and set `reports/sources/bq/connection.yaml` to
`type: duckdb` with `options.filename` pointing at a `.duckdb` file that has a
`fitbit_mart` schema containing the `mart_*` tables (see the SQLMesh models under
`sqlmesh_project/models/marts/` for columns). Then `npm --prefix reports run sources`
and `npm --prefix reports run dev` (serves `http://localhost:3000/pluse-board`).
These are throwaway demo edits — revert them and never commit the seed DB.
