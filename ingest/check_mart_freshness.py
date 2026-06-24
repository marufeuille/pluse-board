"""
Fail CI when the mart tables are not updated for the expected JST date.

Must run AFTER `sqlmesh run` so that the mart is populated before checking.
Checks mart_steps_daily as the primary availability signal.
"""

import argparse
import os
from datetime import date, datetime, timedelta, timezone

from google.cloud import bigquery

JST = timezone(timedelta(hours=9))


def _today_jst() -> date:
    return datetime.now(JST).date()


def _bq_settings() -> tuple[str, str, str]:
    project = os.environ["PROJECT_ID"]
    dataset = os.environ.get("BQ_DATASET_MART") or "fitbit_mart"
    location = os.environ.get("BQ_LOCATION") or "asia-northeast1"
    return project, dataset, location


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected-date",
        default=None,
        help="JST date that must be in the mart (default: yesterday)",
    )
    args = parser.parse_args()

    expected_date = (
        date.fromisoformat(args.expected_date)
        if args.expected_date
        else _today_jst() - timedelta(days=1)
    )

    project, dataset, location = _bq_settings()
    client = bigquery.Client(project=project)

    table_id = f"`{project}.{dataset}.mart_steps_daily`"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("expected_date", "DATE", expected_date),
        ]
    )
    sql = f"SELECT COUNT(*) FROM {table_id} WHERE activity_date = @expected_date"
    rows = list(client.query(sql, job_config=job_config, location=location).result())
    count = rows[0][0] if rows else 0

    if count == 0:
        print(
            f"::error::mart_steps_daily has no row for {expected_date}. "
            "SQLMesh may not have processed the interval yet — check that the "
            "Actions cron aligns with SQLMesh's @daily boundary (UTC midnight)."
        )
        raise SystemExit(1)

    print(f"Mart freshness OK: mart_steps_daily has {count} row(s) for {expected_date}")


if __name__ == "__main__":
    main()
