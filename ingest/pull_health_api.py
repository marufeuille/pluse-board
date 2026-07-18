"""
Google Health API からデータを取得して BigQuery の raw レイヤーに投入する。

使い方:
    python pull_health_api.py --data-type exercise --start 2026-04-01
    python pull_health_api.py --data-type exercise  # 既定: 直近 3 日分
"""

import argparse
import json
import os
from datetime import date, timedelta

from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from requests import HTTPError

from _common import bq_dataset_raw, bq_location, day_ranges, today_jst
from health_api_client import HealthApiClient
from lineage import track_ingest

# BigQuery テーブル名は data_type と同じ（active_zone_minutes → active_zone_minutes）
_TABLE_NAME = {
    "exercise": "exercise",
    "steps": "steps",
    "active_zone_minutes": "active_zone_minutes",
}

ENABLED_DATA_TYPES = ["exercise", "steps", "active_zone_minutes"]

# raw JSON のルートキー (data_type は snake_case だが JSON は camelCase の場合あり)
_JSON_ROOT_KEY = {
    "exercise": "exercise",
    "steps": "steps",
    "active_zone_minutes": "activeZoneMinutes",
}


def _bq_client() -> bigquery.Client:
    return bigquery.Client(project=os.environ["PROJECT_ID"])


def _delete_existing(
    bq: bigquery.Client,
    table_id: str,
    data_type: str,
    start: date,
    end: date,
    location: str,
) -> None:
    """対象期間 [start, end) の civil_start_time に該当する raw を削除する。

    冪等性のため、INSERT の前に必ず実行する。フィルタは API 側 (civil_start_time)
    と揃えてある。テーブルが存在しない場合は何もしない。
    """
    root = _JSON_ROOT_KEY[data_type]
    civil = f"$.{root}.interval.civilStartTime.date"
    sql = f"""
    DELETE FROM `{table_id}`
    WHERE SAFE.DATE(
      CAST(JSON_VALUE(raw, '{civil}.year')  AS INT64),
      CAST(JSON_VALUE(raw, '{civil}.month') AS INT64),
      CAST(JSON_VALUE(raw, '{civil}.day')   AS INT64)
    ) >= @start
    AND   SAFE.DATE(
      CAST(JSON_VALUE(raw, '{civil}.year')  AS INT64),
      CAST(JSON_VALUE(raw, '{civil}.month') AS INT64),
      CAST(JSON_VALUE(raw, '{civil}.day')   AS INT64)
    ) <  @end
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start", "DATE", start),
            bigquery.ScalarQueryParameter("end", "DATE", end),
        ]
    )
    try:
        job = bq.query(sql, job_config=job_config, location=location)
        job.result()
    except NotFound:
        # 初回実行などでテーブルが存在しない場合はスキップ。
        # NotFound 以外のエラーは握りつぶさず伝播させる。
        print(f"  {data_type}: テーブル未作成のため削除スキップ")
        return

    deleted = job.num_dml_affected_rows or 0
    print(f"  {data_type}: 既存 {deleted} 件を削除（{start} – {end}、冪等化）")


def _load_to_bq(
    bq: bigquery.Client,
    rows: list[dict],
    data_type: str,
    start: date,
    end: date,
) -> None:
    dataset, location = bq_dataset_raw(), bq_location()
    table_id = f"{os.environ['PROJECT_ID']}.{dataset}.{_TABLE_NAME[data_type]}"

    # 冪等化: API のソースが信頼できる前提で、まず対象期間の既存レコードを削除する。
    # API が 0 件返した場合も削除は行うので「実は API の返却が空だった」状態にも追従する。
    _delete_existing(bq, table_id, data_type, start, end, location)

    if not rows:
        print(f"  {data_type}: 取得データなし（{start} – {end}）")
        return

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        create_disposition=bigquery.CreateDisposition.CREATE_IF_NEEDED,
        autodetect=True,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    job = bq.load_table_from_json(rows, table_id, job_config=job_config, location=location)
    job.result()

    print(f"  {data_type}: {len(rows)} 件を {table_id} に投入しました")


def _flatten(point: dict) -> dict:
    return {
        "name": point.get("name"),
        "raw": json.dumps(point, ensure_ascii=False),
    }


_FLATTEN = {
    "exercise": _flatten,
    "steps": _flatten,
    "active_zone_minutes": _flatten,
}


def _can_skip_fetch_error(
    error: HTTPError,
    day_start: date,
    required_start: date,
    allow_stale_403: bool,
) -> bool:
    response = error.response
    return (
        allow_stale_403
        and response is not None
        and response.status_code == 403
        and day_start < required_start
    )


def _print_fetch_error_warning(
    data_type: str,
    day_start: date,
    day_end: date,
    error: HTTPError,
) -> None:
    response = error.response
    detail = response.text[:500] if response is not None else str(error)
    print(
        "::warning::"
        f"{data_type} fetch skipped for stale lookback day {day_start} – {day_end}: "
        f"{error}. Response: {detail}"
    )


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
        default=None,
        help="取得開始日 YYYY-MM-DD（未指定時は --lookback-days から算出）",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="取得終了日 YYYY-MM-DD・exclusive（既定: JST の今日）",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=3,
        help="--start 未指定時に取得する直近日数（既定: 3、end は exclusive）",
    )
    args = parser.parse_args()

    if args.lookback_days < 1:
        raise ValueError("--lookback-days must be >= 1")

    today = today_jst()
    end = date.fromisoformat(args.end) if args.end else today
    start = (
        date.fromisoformat(args.start)
        if args.start
        else end - timedelta(days=args.lookback_days)
    )
    required_start = end - timedelta(days=1)
    allow_stale_403 = args.start is None

    if args.data_type == "all":
        targets = ENABLED_DATA_TYPES
    elif args.data_type in ENABLED_DATA_TYPES:
        targets = [args.data_type]
    else:
        print(f"警告: {args.data_type} は現在無効です。ENABLED_DATA_TYPES を確認してください。")
        return

    client = HealthApiClient()
    bq = _bq_client()

    # OpenLineage 用: 出力先 BigQuery テーブルの座標（lineage 無効時は未使用でも害なし）
    dataset = bq_dataset_raw()
    project = os.environ["PROJECT_ID"]

    for dt in targets:
        flatten = _FLATTEN[dt]
        # data_type ごとに 1 run（START→COMPLETE、例外時 FAIL）で lineage を出す。
        # lineage 無効時は完全な no-op なので取り込みには一切影響しない。
        with track_ingest(dt, project, dataset, _TABLE_NAME[dt]):
            for day_start, day_end in day_ranges(start, end):
                print(f"{dt} を取得中 ({day_start} – {day_end}) ...")
                try:
                    rows = [
                        flatten(p)
                        for p in client.fetch_data_points(dt, day_start, day_end)
                    ]
                except HTTPError as e:
                    if _can_skip_fetch_error(e, day_start, required_start, allow_stale_403):
                        _print_fetch_error_warning(dt, day_start, day_end, e)
                        continue
                    raise
                _load_to_bq(bq, rows, dt, day_start, day_end)


if __name__ == "__main__":
    main()
