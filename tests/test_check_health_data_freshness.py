"""Unit tests for ingest/check_health_data_freshness.py."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import check_health_data_freshness as m


# --------------------------------------------------------------------------- #
# _today_jst / _bq_settings
# --------------------------------------------------------------------------- #
def test_today_jst(monkeypatch):
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(m, "datetime", _FrozenDatetime)
    assert m._today_jst() == date(2026, 1, 2)


def test_bq_settings_defaults(monkeypatch):
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.delenv("BQ_DATASET_RAW", raising=False)
    monkeypatch.delenv("BQ_LOCATION", raising=False)
    assert m._bq_settings() == ("proj", "fitbit_raw", "asia-northeast1")


def test_bq_settings_env_override(monkeypatch):
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.setenv("BQ_DATASET_RAW", "raw2")
    monkeypatch.setenv("BQ_LOCATION", "us")
    assert m._bq_settings() == ("proj", "raw2", "us")


def test_bq_settings_missing_project(monkeypatch):
    monkeypatch.delenv("PROJECT_ID", raising=False)
    with pytest.raises(KeyError):
        m._bq_settings()


# --------------------------------------------------------------------------- #
# _scalar
# --------------------------------------------------------------------------- #
class _FakeQueryResult:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class _FakeClient:
    def __init__(self, rows):
        self._rows = rows
        self.queries = []

    def query(self, sql, job_config=None, location=None):
        self.queries.append((sql, location))
        return _FakeQueryResult(self._rows)


def test_scalar_returns_first_cell():
    client = _FakeClient([[7]])
    assert m._scalar(client, "SELECT 1", date(2026, 4, 1), "asia-northeast1") == 7
    assert client.queries[0][1] == "asia-northeast1"


def test_scalar_returns_none_for_empty():
    client = _FakeClient([])
    assert m._scalar(client, "SELECT 1", date(2026, 4, 1), "asia-northeast1") is None


# --------------------------------------------------------------------------- #
# _error / _warning
# --------------------------------------------------------------------------- #
def test_error_and_warning_format(capsys):
    m._error("bad")
    m._warning("meh")
    out = capsys.readouterr().out
    assert "::error::bad" in out
    assert "::warning::meh" in out


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
@pytest.fixture
def _main_env(monkeypatch):
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.setenv("BQ_DATASET_RAW", "fitbit_raw")
    monkeypatch.setenv("BQ_LOCATION", "asia-northeast1")
    monkeypatch.setattr(m.bigquery, "Client", lambda project=None: object())
    monkeypatch.setattr("sys.argv", ["prog", "--expected-date", "2026-04-01"])


def _patch_scalars(monkeypatch, steps, exercise_azm, azm):
    """Script _scalar's three sequential calls: steps, exercise AZM, azm rows."""
    values = iter([steps, exercise_azm, azm])
    monkeypatch.setattr(m, "_scalar", lambda *a, **k: next(values))


def test_main_ok(monkeypatch, _main_env, capsys):
    _patch_scalars(monkeypatch, steps=100, exercise_azm=30, azm=5)
    m.main()
    out = capsys.readouterr().out
    assert "Health data freshness OK" in out
    assert "steps_rows=100" in out


def test_main_missing_steps_exits(monkeypatch, _main_env, capsys):
    _patch_scalars(monkeypatch, steps=0, exercise_azm=0, azm=0)
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    assert "FITBIT steps data is missing" in capsys.readouterr().out


def test_main_azm_missing_but_expected_exits(monkeypatch, _main_env, capsys):
    # exercise reports positive AZM but active-zone-minutes rows are absent.
    _patch_scalars(monkeypatch, steps=100, exercise_azm=42, azm=0)
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    assert "active-zone-minutes data is missing" in capsys.readouterr().out


def test_main_zero_load_day_warns(monkeypatch, _main_env, capsys):
    # No AZM rows and no exercise AZM => valid zero-load day, only a warning.
    _patch_scalars(monkeypatch, steps=100, exercise_azm=0, azm=0)
    m.main()
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "Health data freshness OK" in out


def test_main_defaults_to_yesterday(monkeypatch):
    monkeypatch.setenv("PROJECT_ID", "proj")
    monkeypatch.setattr(m.bigquery, "Client", lambda project=None: object())
    monkeypatch.setattr(m, "_today_jst", lambda: date(2026, 4, 10))
    monkeypatch.setattr("sys.argv", ["prog"])
    captured = {}

    def _fake_scalar(client, sql, expected_date, location):
        captured["expected_date"] = expected_date
        return 1

    monkeypatch.setattr(m, "_scalar", _fake_scalar)
    m.main()
    assert captured["expected_date"] == date(2026, 4, 9)
