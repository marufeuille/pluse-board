You are triaging a failed GitHub Actions Daily Build for this repository.

Read these files first:

- `AGENTS.md`
- `daily-build-context.md`
- `failed-run.log`
- Relevant workflow, dbt, reports, or dependency files referenced by the log

Follow the automation boundaries in `AGENTS.md`.
The log may come from a real failed run or from a synthetic dry-run test case.
Use `daily-build-context.md` to tell which mode is being tested, but classify
the failure from the evidence in `failed-run.log`.

Classify the failure as exactly one of:

- `transient_retryable`: a likely temporary GitHub, network, registry, API, or runner issue where rerunning failed jobs once is the safest next step.
- `code_or_lockfile_fixable`: an obvious repository code, workflow, dependency metadata, or lockfile issue that can likely be fixed with a minimal PR.
- `dbt_or_report_fixable`: an obvious dbt model, Evidence source/page, SQL, or report build issue that can likely be fixed with a minimal PR.
- `credentials_or_gcp_manual`: likely caused by GCP IAM, WIF, GitHub Secrets, GitHub Variables, Pages settings, or credentials.
- `health_api_or_data_manual`: likely caused by Health API availability, token refresh, upstream data freshness, or BigQuery data freshness.
- `unknown_manual`: not enough evidence to safely automate a retry or patch.

Set `should_rerun` to true only for `transient_retryable`.
Set `should_open_pr` to true only for `code_or_lockfile_fixable` or `dbt_or_report_fixable` when the log points to a concrete, minimal repository change.

Never recommend changing secrets, GitHub repository settings, branch protection, GCP IAM, Workload Identity Federation, GitHub Variables, or Pages settings automatically.

Return only JSON matching the schema.
