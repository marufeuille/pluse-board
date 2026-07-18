"""Unit tests for ingest/_common.py."""

from __future__ import annotations

from datetime import date

import _common as m


# --------------------------------------------------------------------------- #
# today_jst
# --------------------------------------------------------------------------- #
def test_today_jst_uses_jst_offset(monkeypatch):
    # 2026-01-01 23:00 UTC is already 2026-01-02 08:00 in JST (+9h).
    from datetime import datetime, timezone

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(m, "datetime", _FrozenDatetime)
    assert m.today_jst() == date(2026, 1, 2)


# --------------------------------------------------------------------------- #
# bq_dataset_raw / bq_location
# --------------------------------------------------------------------------- #
def test_bq_settings_defaults(monkeypatch):
    monkeypatch.delenv("BQ_DATASET_RAW", raising=False)
    monkeypatch.delenv("BQ_LOCATION", raising=False)
    assert m.bq_dataset_raw() == "fitbit_raw"
    assert m.bq_location() == "asia-northeast1"


def test_bq_settings_env_override(monkeypatch):
    monkeypatch.setenv("BQ_DATASET_RAW", "custom_raw")
    monkeypatch.setenv("BQ_LOCATION", "us-central1")
    assert m.bq_dataset_raw() == "custom_raw"
    assert m.bq_location() == "us-central1"


def test_bq_settings_empty_env_falls_back(monkeypatch):
    # Empty string should fall back to the default (``or`` handles falsy values).
    monkeypatch.setenv("BQ_DATASET_RAW", "")
    monkeypatch.setenv("BQ_LOCATION", "")
    assert m.bq_dataset_raw() == "fitbit_raw"
    assert m.bq_location() == "asia-northeast1"


# --------------------------------------------------------------------------- #
# day_ranges
# --------------------------------------------------------------------------- #
def test_day_ranges_splits_into_single_days():
    ranges = m.day_ranges(date(2026, 4, 1), date(2026, 4, 4))
    assert ranges == [
        (date(2026, 4, 1), date(2026, 4, 2)),
        (date(2026, 4, 2), date(2026, 4, 3)),
        (date(2026, 4, 3), date(2026, 4, 4)),
    ]


def test_day_ranges_empty_when_start_ge_end():
    assert m.day_ranges(date(2026, 4, 4), date(2026, 4, 4)) == []
    assert m.day_ranges(date(2026, 4, 5), date(2026, 4, 4)) == []


def test_day_ranges_single_day():
    assert m.day_ranges(date(2026, 4, 1), date(2026, 4, 2)) == [
        (date(2026, 4, 1), date(2026, 4, 2))
    ]
