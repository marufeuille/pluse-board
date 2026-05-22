"""
Google Health API からデータを取得して BigQuery の raw レイヤーに投入する。

使い方:
    python pull_health_api.py --data-type exercise --start 2026-04-01
    python pull_health_api.py --data-type exercise  # 既定: 直近 3 日分
"""

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone

from google.cloud import bigquery

from health_api_client import HealthApiClient

# データ取得範囲のデフォルトは civil_start_time（= JST）基準で決める。
# GitHub Actions ランナーの OS TZ は UTC なので、素の date.today() を使うと
# 深夜帯（03:00 JST = 18:00 UTC）に「一昨日」を取りに行く事故が起きる。
JST = timezone(timedelta(hours=9))


def _today_jst() -> date:
    return datetime.now(JST).date()

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


def _bq_settings() -> tuple[str, str]:
    dataset = os.environ.get("BQ_DATASET_RAW") or "fitbit_raw"
    location = os.environ.get("BQ_LOCATION") or "asia-northeast1"
    return dataset, location


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
    except Exception as e:
        # 初回実行などでテーブルが存在しない場合はスキップ
        if "Not found" in str(e):
            print(f"  {data_type}: テーブル未作成のため削除スキップ")
            return
        raise

    deleted = job.num_dml_affected_rows or 0
    print(f"  {data_type}: 既存 {deleted} 件を削除（{start} – {end}、冪等化）")


def _load_to_bq(
    bq: bigquery.Client,
    rows: list[dict],
    data_type: str,
    start: date,
    end: date,
) -> None:
    dataset, location = _bq_settings()
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

    today = _today_jst()
    end = date.fromisoformat(args.end) if args.end else today
    start = (
        date.fromisoformat(args.start)
        if args.start
        else end - timedelta(days=args.lookback_days)
    )

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
