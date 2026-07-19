# Daily Build Triage Test Patterns

The `Daily Build Triage` workflow can be tested manually from GitHub Actions
without forcing `Daily Build` to fail.

Before testing, add repository secret `CLAUDE_CODE_OAUTH_TOKEN`
(generate it with `claude setup-token`).

## Dry-run synthetic tests

Open **Actions -> Daily Build Triage -> Run workflow** and leave `run_id` empty.
Keep `dry_run` set to `true`, then choose one `test_case`.

| test_case | Expected behavior |
| --- | --- |
| `transient_network` | Claude should classify the log as `transient_retryable`. Because this is a dry run, no rerun is started. |
| `report_dependency` | Claude should classify the log as a fixable report or lockfile issue and may generate a patch artifact. No PR is opened in dry run mode. |
| `dbt_sql` | Claude should classify the log as `dbt_or_report_fixable` and may generate a patch artifact. No PR is opened in dry run mode. |
| `gcp_wif_manual` | Claude should classify the log as `credentials_or_gcp_manual`. No rerun, patch PR, or issue is created in dry run mode. |
| `health_data_manual` | Claude should classify the log as `health_api_or_data_manual`. No rerun, patch PR, or issue is created in dry run mode. |

Artifacts to inspect:

- `daily-build-triage`
- `daily-build-claude-patch`, only when Claude generated a patch
- `daily-build-claude-patch-summary`, when patch generation ran

## Dry-run against a real failed run

Use the failed `Daily Build` run ID as `run_id`, leave `test_case` as `none`,
and keep `dry_run` set to `true`.

Expected behavior:

- The workflow downloads the real failed run logs.
- Claude writes `triage.json`.
- No rerun, PR, or issue is created.

## End-to-end controlled run

Use a real failed `Daily Build` run ID, set `test_case` to `none`, and set
`dry_run` to `false`.

Expected behavior:

- `transient_retryable`: reruns failed jobs once, only when the failed run was
  attempt 1.
- `code_or_lockfile_fixable` or `dbt_or_report_fixable`: generates a patch
  artifact and opens a PR if a patch exists.
- Manual categories: creates or updates a follow-up issue.

Do not use `dry_run=false` with synthetic test cases. The workflow rejects
manual non-dry-run executions that do not provide a `run_id`.
