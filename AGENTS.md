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
