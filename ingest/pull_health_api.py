"""
Google Health API からデータを取得して BigQuery の raw レイヤーに投入する。

使い方:
    python pull_health_api.py --data-type exercise --start 2026-04-01
    python pull_health_api.py --data-type exercise  # 既定: 昨日 1 日分
"""

import argparse
import json
import os
from datetime import date, timedelta

from google.cloud import bigquery

from health_api_client import HealthApiClient

# BigQuery テーブル名は data_type と同じ（active_zone_minutes → active_zone_minutes）
_TABLE_NAME = {
    "exercise": "exercise",
    "steps": "steps",
    "active_zone_minutes": "active_zone_minutes",
}

ENABLED_DATA_TYPES = ["exercise", "steps", "active_zone_minutes"]


def _bq_client() -> bigquery.Client:
    return bigquery.Client(project=os.environ["PROJECT_ID"])


def _load_to_bq(
    bq: bigquery.Client,
    rows: list[dict],
    data_type: str,
    start: date,
    end: date,
) -> None:
    dataset = os.environ.get("BQ_DATASET_RAW", "fitbit_raw")
    table_id = f"{os.environ['PROJECT_ID']}.{dataset}.{_TABLE_NAME[data_type]}"
    location = os.environ.get("BQ_LOCATION", "asia-northeast1")

    # 対象期間のデータを削除してから INSERT（べき等）
    delete_sql = f"""
        DELETE FROM `{table_id}`
        WHERE DATE(interval_civil_start_time) >= '{start}'
          AND DATE(interval_civil_start_time) <  '{end}'
    """
    job_config = bigquery.QueryJobConfig()
    bq.query(delete_sql, job_config=job_config, location=location).result()

    if not rows:
        print(f"  {data_type}: データなし（{start} – {end}）")
        return

    errors = bq.insert_rows_json(table_id, rows)
    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")

    print(f"  {data_type}: {len(rows)} 件を {table_id} に投入しました")


def _flatten_exercise(point: dict) -> dict:
    interval = point.get("interval", {})
    values = {v["id"]: v.get("fpVal") or v.get("intVal") or v.get("stringVal")
              for v in point.get("value", [])}
    return {
        "interval_civil_start_time": interval.get("civilStartTime"),
        "interval_civil_end_time": interval.get("civilEndTime"),
        "activity_type": values.get("activity"),
        "activity_name": values.get("activityName"),
        "duration_ms": values.get("duration"),
        "calories": values.get("calories"),
        "distance_m": values.get("distance"),
        "raw": json.dumps(point),
    }


def _flatten_steps(point: dict) -> dict:
    interval = point.get("interval", {})
    values = {v["id"]: v.get("fpVal") or v.get("intVal")
              for v in point.get("value", [])}
    return {
        "interval_civil_start_time": interval.get("civilStartTime"),
        "interval_civil_end_time": interval.get("civilEndTime"),
        "steps": values.get("steps"),
        "raw": json.dumps(point),
    }


def _flatten_active_zone_minutes(point: dict) -> dict:
    interval = point.get("interval", {})
    values = {v["id"]: v.get("fpVal") or v.get("intVal")
              for v in point.get("value", [])}
    return {
        "interval_civil_start_time": interval.get("civilStartTime"),
        "interval_civil_end_time": interval.get("civilEndTime"),
        "value": values.get("activeZoneMinutes"),
        "raw": json.dumps(point),
    }


_FLATTEN = {
    "exercise": _flatten_exercise,
    "steps": _flatten_steps,
    "active_zone_minutes": _flatten_active_zone_minutes,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-type",
        choices=list(_TABLE_NAME.keys()) + ["all"],
        default="all",
        help="取得するデータタイプ（既定: all だが ENABLED_DATA_TYPES の範囲内）",
    )
    parser.add_argument(
        "--start",
        default=str(date.today() - timedelta(days=1)),
        help="取得開始日 YYYY-MM-DD（既定: 昨日）",
    )
    parser.add_argument(
        "--end",
        default=str(date.today()),
        help="取得終了日 YYYY-MM-DD・exclusive（既定: 今日）",
    )
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if args.data_type == "all":
        targets = ENABLED_DATA_TYPES
    elif args.data_type in ENABLED_DATA_TYPES:
        targets = [args.data_type]
    else:
        print(f"警告: {args.data_type} は現在無効です。ENABLED_DATA_TYPES を確認してください。")
        return

    client = HealthApiClient()
    bq = _bq_client()

    for dt in targets:
        print(f"{dt} を取得中 ({start} – {end}) ...")
        flatten = _FLATTEN[dt]
        rows = [flatten(p) for p in client.fetch_data_points(dt, start, end)]
        _load_to_bq(bq, rows, dt, start, end)


if __name__ == "__main__":
    main()
