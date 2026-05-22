"""
Fail CI when the latest completed JST day was not ingested.

This is intentionally conservative:
- steps must exist for the expected date because they are the best availability
  signal for "the day was synced".
- active-zone-minutes are allowed to be absent when exercise summaries report
  zero AZM for that date, because zero-load days are valid ACWR inputs.
- if exercise summaries report positive AZM but active-zone-minutes are absent,
  fail because ACWR would understate the load.
"""

import argparse
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from google.cloud import bigquery

JST = timezone(timedelta(hours=9))


def _today_jst() -> date:
    return datetime.now(JST).date()


def _bq_settings() -> tuple[str, str, str]:
    project = os.environ["PROJECT_ID"]
    dataset = os.environ.get("BQ_DATASET_RAW") or "fitbit_raw"
    location = os.environ.get("BQ_LOCATION") or "asia-northeast1"
    return project, dataset, location


def _scalar(
    client: bigquery.Client,
    sql: str,
    expected_date: date,
    location: str,
) -> Any:
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("expected_date", "DATE", expected_date),
        ]
    )
    rows = list(client.query(sql, job_config=job_config, location=location).result())
    return rows[0][0] if rows else None


def _error(message: str) -> None:
    print(f"::error::{message}")


def _warning(message: str) -> None:
    print(f"::warning::{message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected-date",
        default=None,
        help="Completed JST date that must be available (default: yesterday)",
    )
    args = parser.parse_args()

    expected_date = (
        date.fromisoformat(args.expected_date)
        if args.expected_date
        else _today_jst() - timedelta(days=1)
    )

    project, dataset, location = _bq_settings()
    client = bigquery.Client(project=project)

    steps_table = f"`{project}.{dataset}.steps`"
    exercise_table = f"`{project}.{dataset}.exercise`"
    azm_table = f"`{project}.{dataset}.active_zone_minutes`"

    steps_count = _scalar(
        client,
        f"""
        SELECT COUNT(*)
        FROM {steps_table}
        WHERE JSON_VALUE(raw, '$.dataSource.platform') = 'FITBIT'
          AND DATE(TIMESTAMP(JSON_VALUE(raw, '$.steps.interval.startTime')), 'Asia/Tokyo')
              = @expected_date
        """,
        expected_date,
        location,
    )
    if steps_count == 0:
        _error(f"FITBIT steps data is missing for {expected_date}.")
        raise SystemExit(1)

    exercise_azm = _scalar(
        client,
        f"""
        SELECT COALESCE(SUM(CAST(JSON_VALUE(
          raw,
          '$.exercise.metricsSummary.activeZoneMinutes'
        ) AS INT64)), 0)
        FROM {exercise_table}
        WHERE DATE(TIMESTAMP(JSON_VALUE(raw, '$.exercise.interval.startTime')), 'Asia/Tokyo')
              = @expected_date
        """,
        expected_date,
        location,
    )

    azm_count = _scalar(
        client,
        f"""
        SELECT COUNT(*)
        FROM {azm_table}
        WHERE DATE(
          TIMESTAMP(JSON_VALUE(raw, '$.activeZoneMinutes.interval.startTime')),
          'Asia/Tokyo'
        ) = @expected_date
        """,
        expected_date,
        location,
    )

    if exercise_azm > 0 and azm_count == 0:
        _error(
            "active-zone-minutes data is missing for "
            f"{expected_date}, but exercise summaries report {exercise_azm} AZM."
        )
        raise SystemExit(1)

    if azm_count == 0:
        _warning(
            "active-zone-minutes has no rows for "
            f"{expected_date}; treating the day as zero load."
        )

    print(
        "Health data freshness OK: "
        f"date={expected_date}, steps_rows={steps_count}, "
        f"exercise_azm={exercise_azm}, azm_rows={azm_count}"
    )


if __name__ == "__main__":
    main()
