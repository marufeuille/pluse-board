You are preparing a minimal patch for a failed GitHub Actions Daily Build.

Read these files first:

- `AGENTS.md`
- `.codex-runtime/daily-build-context.md`
- `.codex-runtime/failed-run.log`
- `.codex-runtime/codex-triage.json`
- Relevant repository files referenced by the log and triage result

Follow the automation boundaries in `AGENTS.md`.

Only edit repository files when the triage result is `code_or_lockfile_fixable` or `dbt_or_report_fixable` and the log points to a concrete, minimal fix. Keep the patch narrowly scoped.

Do not edit secrets, credentials, local profiles, generated build output, downloaded data, GitHub repository settings, branch protection, GCP IAM, Workload Identity Federation, GitHub Secrets, GitHub Variables, or Pages settings.

If the failure is likely related to Health API availability, token refresh, BigQuery data freshness, GCP IAM, WIF, GitHub Pages settings, GitHub Secrets, or GitHub Variables, leave the working tree unchanged and explain why.

Run the smallest relevant local/static checks available after editing. If a check cannot run because it needs external credentials, network access, Docker daemon access, or GCP access, say that in your final message and run the closest local/static check instead.

Do not commit, push, create branches, create pull requests, or delete unrelated files.
