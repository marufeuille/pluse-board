"""Unit tests for ingest/pull_health_api.py."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from requests import HTTPError

import pull_health_api as m


# --------------------------------------------------------------------------- #
# _today_jst
# --------------------------------------------------------------------------- #
def test_today_jst_uses_jst_offset(monkeypatch):
    # 2026-01-01 23:00 UTC is already 2026-01-02 08:00 in JST (+9h).
    from datetime import datetime, timezone

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(m, "datetime", _FrozenDatetime)
    assert m._today_jst() == date(2026, 1, 2)


# --------------------------------------------------------------------------- #
# _bq_settings
# --------------------------------------------------------------------------- #
def test_bq_settings_defaults(monkeypatch):
    monkeypatch.delenv("BQ_DATASET_RAW", raising=False)
    monkeypatch.delenv("BQ_LOCATION", raising=False)
    assert m._bq_settings() == ("fitbit_raw", "asia-northeast1")


def test_bq_settings_env_override(monkeypatch):
    monkeypatch.setenv("BQ_DATASET_RAW", "custom_raw")
    monkeypatch.setenv("BQ_LOCATION", "us-central1")
    assert m._bq_settings() == ("custom_raw", "us-central1")


def test_bq_settings_empty_env_falls_back(monkeypatch):
    # Empty string should fall back to the default (``or`` handles falsy values).
    monkeypatch.setenv("BQ_DATASET_RAW", "")
    monkeypatch.setenv("BQ_LOCATION", "")
    assert m._bq_settings() == ("fitbit_raw", "asia-northeast1")


# --------------------------------------------------------------------------- #
# _flatten
# --------------------------------------------------------------------------- #
def test_flatten_keeps_name_and_serialises_raw():
    point = {"name": "点1", "value": 42}
    out = m._flatten(point)
    assert out["name"] == "点1"
    # ensure_ascii=False keeps non-ASCII characters readable.
    assert "点1" in out["raw"]
    assert '"value": 42' in out["raw"]


def test_flatten_missing_name_is_none():
    assert m._flatten({"value": 1})["name"] is None


# --------------------------------------------------------------------------- #
# _day_ranges
# --------------------------------------------------------------------------- #
def test_day_ranges_splits_into_single_days():
    ranges = m._day_ranges(date(2026, 4, 1), date(2026, 4, 4))
    assert ranges == [
        (date(2026, 4, 1), date(2026, 4, 2)),
        (date(2026, 4, 2), date(2026, 4, 3)),
        (date(2026, 4, 3), date(2026, 4, 4)),
    ]


def test_day_ranges_empty_when_start_ge_end():
    assert m._day_ranges(date(2026, 4, 4), date(2026, 4, 4)) == []
    assert m._day_ranges(date(2026, 4, 5), date(2026, 4, 4)) == []


def test_day_ranges_single_day():
    assert m._day_ranges(date(2026, 4, 1), date(2026, 4, 2)) == [
        (date(2026, 4, 1), date(2026, 4, 2))
    ]


# --------------------------------------------------------------------------- #
# _can_skip_fetch_error
# --------------------------------------------------------------------------- #
def _http_error(status_code=None, text="boom"):
    if status_code is None:
        response = None
    else:
        response = SimpleNamespace(status_code=status_code, text=text)
    err = HTTPError("boom")
    err.response = response
    return err


def test_can_skip_fetch_error_true_for_stale_403():
    err = _http_error(403)
    assert m._can_skip_fetch_error(
        err, date(2026, 4, 1), required_start=date(2026, 4, 3), allow_stale_403=True
    )


def test_can_skip_fetch_error_false_when_not_allowed():
    err = _http_error(403)
    assert not m._can_skip_fetch_error(
        err, date(2026, 4, 1), required_start=date(2026, 4, 3), allow_stale_403=False
    )


def test_can_skip_fetch_error_false_for_non_403():
    err = _http_error(500)
    assert not m._can_skip_fetch_error(
        err, date(2026, 4, 1), required_start=date(2026, 4, 3), allow_stale_403=True
    )


def test_can_skip_fetch_error_false_for_required_day():
    # A day at/after required_start must never be skipped.
    err = _http_error(403)
    assert not m._can_skip_fetch_error(
        err, date(2026, 4, 3), required_start=date(2026, 4, 3), allow_stale_403=True
    )


def test_can_skip_fetch_error_false_when_no_response():
    err = _http_error(None)
    assert not m._can_skip_fetch_error(
        err, date(2026, 4, 1), required_start=date(2026, 4, 3), allow_stale_403=True
    )


# --------------------------------------------------------------------------- #
# _print_fetch_error_warning
# --------------------------------------------------------------------------- #
def test_print_fetch_error_warning_with_response(capsys):
    err = _http_error(403, text="x" * 1000)
    m._print_fetch_error_warning("steps", date(2026, 4, 1), date(2026, 4, 2), err)
    out = capsys.readouterr().out
    assert out.startswith("::warning::")
    assert "steps fetch skipped" in out
    # Response text is truncated to 500 characters.
    assert "x" * 500 in out
    assert "x" * 501 not in out


def test_print_fetch_error_warning_without_response(capsys):
    err = _http_error(None)
    m._print_fetch_error_warning("steps", date(2026, 4, 1), date(2026, 4, 2), err)
    assert "::warning::" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# _delete_existing
# --------------------------------------------------------------------------- #
class _FakeJob:
    def __init__(self, affected=3):
        self.num_dml_affected_rows = affected

    def result(self):
        return None


class _FakeBQ:
    def __init__(self):
        self.query_calls = []
        self.load_calls = []
        self._query_job = _FakeJob()
        self._query_error = None

    def query(self, sql, job_config=None, location=None):
        self.query_calls.append((sql, job_config, location))
        if self._query_error is not None:
            raise self._query_error
        return self._query_job

    def load_table_from_json(self, rows, table_id, job_config=None, location=None):
        self.load_calls.append((rows, table_id, location))
        return _FakeJob()


def test_delete_existing_runs_query(capsys):
    bq = _FakeBQ()
    m._delete_existing(
        bq, "proj.ds.steps", "steps", date(2026, 4, 1), date(2026, 4, 2), "asia-northeast1"
    )
    assert len(bq.query_calls) == 1
    sql, _cfg, location = bq.query_calls[0]
    assert "DELETE FROM `proj.ds.steps`" in sql
    assert location == "asia-northeast1"
    assert "既存 3 件を削除" in capsys.readouterr().out


def test_delete_existing_skips_when_table_missing(capsys):
    bq = _FakeBQ()
    bq._query_error = Exception("404 Not found: table")
    m._delete_existing(
        bq, "proj.ds.steps", "steps", date(2026, 4, 1), date(2026, 4, 2), "asia-northeast1"
    )
    assert "削除スキップ" in capsys.readouterr().out


def test_delete_existing_reraises_other_errors():
    bq = _FakeBQ()
    bq._query_error = Exception("permission denied")
    with pytest.raises(Exception, match="permission denied"):
        m._delete_existing(
            bq, "proj.ds.steps", "steps", date(2026, 4, 1), date(2026, 4, 2), "asia-northeast1"
        )


# --------------------------------------------------------------------------- #
# _load_to_bq
# --------------------------------------------------------------------------- #
def test_load_to_bq_appends_rows(monkeypatch, capsys):
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.setenv("BQ_DATASET_RAW", "fitbit_raw")
    monkeypatch.setenv("BQ_LOCATION", "asia-northeast1")
    bq = _FakeBQ()
    rows = [{"name": "a", "raw": "{}"}]
    m._load_to_bq(bq, rows, "steps", date(2026, 4, 1), date(2026, 4, 2))
    assert len(bq.query_calls) == 1  # delete first
    assert len(bq.load_calls) == 1
    loaded_rows, table_id, location = bq.load_calls[0]
    assert loaded_rows == rows
    assert table_id == "proj.fitbit_raw.steps"
    assert location == "asia-northeast1"
    assert "1 件を proj.fitbit_raw.steps に投入" in capsys.readouterr().out


def test_load_to_bq_no_rows_skips_load(monkeypatch, capsys):
    monkeypatch.setenv("PROJECT_ID", "proj")
    bq = _FakeBQ()
    m._load_to_bq(bq, [], "steps", date(2026, 4, 1), date(2026, 4, 2))
    assert len(bq.load_calls) == 0  # nothing to load
    assert "取得データなし" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
class _FakeClient:
    def __init__(self, points):
        self._points = points
        self.calls = []

    def fetch_data_points(self, data_type, start, end):
        self.calls.append((data_type, start, end))
        return list(self._points)


@pytest.fixture
def _patched_main(monkeypatch):
    """Patch out external dependencies of ``main`` and record what it does."""
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.setenv("BQ_DATASET_RAW", "fitbit_raw")
    monkeypatch.setenv("BQ_LOCATION", "asia-northeast1")

    fake_bq = _FakeBQ()
    loaded: list = []

    def _fake_load(bq, rows, dt, start, end):
        loaded.append((dt, list(rows), start, end))

    from contextlib import contextmanager

    @contextmanager
    def _noop_track(*_args, **_kwargs):
        yield

    monkeypatch.setattr(m, "_bq_client", lambda: fake_bq)
    monkeypatch.setattr(m, "_load_to_bq", _fake_load)
    monkeypatch.setattr(m, "_today_jst", lambda: date(2026, 4, 10))
    monkeypatch.setattr(m, "track_ingest", _noop_track)
    return SimpleNamespace(bq=fake_bq, loaded=loaded)


def test_main_lookback_default_range(monkeypatch, _patched_main):
    client = _FakeClient([{"name": "p"}])
    monkeypatch.setattr(m, "HealthApiClient", lambda: client)
    monkeypatch.setattr("sys.argv", ["prog", "--data-type", "steps"])
    m.main()
    # Default lookback is 3 days ending at (exclusive) today => Apr 7,8,9.
    fetched_days = [(s, e) for (_dt, s, e) in client.calls]
    assert fetched_days == [
        (date(2026, 4, 7), date(2026, 4, 8)),
        (date(2026, 4, 8), date(2026, 4, 9)),
        (date(2026, 4, 9), date(2026, 4, 10)),
    ]
    assert len(_patched_main.loaded) == 3


def test_main_explicit_start_end(monkeypatch, _patched_main):
    client = _FakeClient([{"name": "p"}])
    monkeypatch.setattr(m, "HealthApiClient", lambda: client)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--data-type", "steps", "--start", "2026-04-01", "--end", "2026-04-03"],
    )
    m.main()
    fetched_days = [(s, e) for (_dt, s, e) in client.calls]
    assert fetched_days == [
        (date(2026, 4, 1), date(2026, 4, 2)),
        (date(2026, 4, 2), date(2026, 4, 3)),
    ]


def test_main_all_iterates_enabled_types(monkeypatch, _patched_main):
    client = _FakeClient([{"name": "p"}])
    monkeypatch.setattr(m, "HealthApiClient", lambda: client)
    monkeypatch.setattr("sys.argv", ["prog", "--start", "2026-04-01", "--end", "2026-04-02"])
    m.main()
    fetched_types = {dt for (dt, _s, _e) in client.calls}
    assert fetched_types == set(m.ENABLED_DATA_TYPES)


def test_main_rejects_bad_lookback(monkeypatch, _patched_main):
    monkeypatch.setattr(m, "HealthApiClient", lambda: _FakeClient([]))
    monkeypatch.setattr("sys.argv", ["prog", "--lookback-days", "0"])
    with pytest.raises(ValueError, match="lookback-days"):
        m.main()


def test_main_skips_stale_403(monkeypatch, _patched_main, capsys):
    # First (stale) day raises 403 and should be skipped; the required day loads.
    class _RaisingClient:
        def __init__(self):
            self.calls = []

        def fetch_data_points(self, data_type, start, end):
            self.calls.append((data_type, start, end))
            if start == date(2026, 4, 8):
                raise _http_error(403)
            return [{"name": "ok"}]

    client = _RaisingClient()
    monkeypatch.setattr(m, "HealthApiClient", lambda: client)
    # today=Apr 10, lookback 2 => Apr 8 (stale) and Apr 9 (required).
    monkeypatch.setattr("sys.argv", ["prog", "--data-type", "steps", "--lookback-days", "2"])
    m.main()
    loaded_days = [(s, e) for (_dt, rows, s, e) in _patched_main.loaded]
    assert loaded_days == [(date(2026, 4, 9), date(2026, 4, 10))]
    assert "::warning::" in capsys.readouterr().out


def test_main_reraises_non_skippable_error(monkeypatch, _patched_main):
    class _RaisingClient:
        def fetch_data_points(self, data_type, start, end):
            raise _http_error(500)

    monkeypatch.setattr(m, "HealthApiClient", lambda: _RaisingClient())
    # explicit --start disables stale-403 skipping entirely.
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--data-type", "steps", "--start", "2026-04-01", "--end", "2026-04-02"],
    )
    with pytest.raises(HTTPError):
        m.main()
