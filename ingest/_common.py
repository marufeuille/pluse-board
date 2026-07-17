"""ingest スクリプト共通の小さなユーティリティ。

JST 基準の日付計算・BigQuery 接続設定・日次レンジ分割は複数の ingest
スクリプトで重複していたため、ここに 1 箇所へ集約する。
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

# GitHub Actions ランナーの OS TZ は UTC。civil_start_time(= JST) 基準で日付を
# 決めないと、深夜帯（03:00 JST = 18:00 UTC）に「一昨日」を取りに行く事故が
# 起きる。取得範囲・鮮度チェックの基準日はすべて JST で判定する。
JST = timezone(timedelta(hours=9))

_DEFAULT_DATASET_RAW = "fitbit_raw"
_DEFAULT_BQ_LOCATION = "asia-northeast1"


def today_jst() -> date:
    """JST の今日を返す。"""
    return datetime.now(JST).date()


def bq_dataset_raw() -> str:
    """raw レイヤーの BigQuery データセット名（未設定時は既定値）。"""
    return os.environ.get("BQ_DATASET_RAW") or _DEFAULT_DATASET_RAW


def bq_location() -> str:
    """BigQuery ジョブのロケーション（未設定時は既定値）。"""
    return os.environ.get("BQ_LOCATION") or _DEFAULT_BQ_LOCATION


def day_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """[start, end) を 1 日単位の [day_start, day_end) 区間へ分割する。

    Health API は長期間リクエストで 503 を返しやすいので、呼び出し側は
    この 1 日区間ごとにリクエスト・投入する。
    """
    ranges: list[tuple[date, date]] = []
    current = start
    while current < end:
        next_day = min(current + timedelta(days=1), end)
        ranges.append((current, next_day))
        current = next_day
    return ranges
