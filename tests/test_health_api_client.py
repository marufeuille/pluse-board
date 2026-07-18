"""Unit tests for ingest/health_api_client.py."""

from __future__ import annotations

from datetime import date

import pytest

import health_api_client as m


@pytest.fixture
def _creds_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_HEALTH_REFRESH_TOKEN", "rt")
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_SECRET", "secret")


class _FakeResponse:
    def __init__(self, *, status_code=200, json_body=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import HTTPError

            err = HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err


def _client(monkeypatch, responses):
    """Build a client whose token is stubbed and requests.get is scripted."""
    client = m.HealthApiClient.__new__(m.HealthApiClient)
    monkeypatch.setattr(client, "_access_token", lambda: "token", raising=False)
    it = iter(responses)
    calls = []

    def _fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers})
        return next(it)

    monkeypatch.setattr(m.requests, "get", _fake_get)
    monkeypatch.setattr(m.time, "sleep", lambda *_a, **_k: None)
    return client, calls


# --------------------------------------------------------------------------- #
# _build_credentials
# --------------------------------------------------------------------------- #
def test_build_credentials_reads_env(_creds_env):
    creds = m._build_credentials()
    assert creds.refresh_token == "rt"
    assert creds.client_id == "cid"
    assert creds.client_secret == "secret"
    assert creds.token_uri == m.TOKEN_URI


def test_build_credentials_missing_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_HEALTH_REFRESH_TOKEN", raising=False)
    with pytest.raises(KeyError):
        m._build_credentials()


# --------------------------------------------------------------------------- #
# _access_token
# --------------------------------------------------------------------------- #
def test_access_token_refreshes_when_invalid(_creds_env, monkeypatch):
    client = m.HealthApiClient()
    refreshed = {"called": False}

    class _Creds:
        valid = False
        token = "fresh"

        def refresh(self, _request):
            refreshed["called"] = True
            self.valid = True

    client._creds = _Creds()
    assert client._access_token() == "fresh"
    assert refreshed["called"] is True


def test_access_token_reuses_valid_token(_creds_env):
    client = m.HealthApiClient()

    class _Creds:
        valid = True
        token = "cached"

        def refresh(self, _request):  # pragma: no cover - must not be called
            raise AssertionError("should not refresh a valid token")

    client._creds = _Creds()
    assert client._access_token() == "cached"


# --------------------------------------------------------------------------- #
# fetch_data_points / _fetch_chunk
# --------------------------------------------------------------------------- #
def test_fetch_data_points_single_page(monkeypatch):
    resp = _FakeResponse(json_body={"dataPoints": [{"name": "a"}, {"name": "b"}]})
    client, calls = _client(monkeypatch, [resp])
    points = list(client.fetch_data_points("steps", date(2026, 4, 1), date(2026, 4, 2)))
    assert points == [{"name": "a"}, {"name": "b"}]
    assert calls[0]["url"].endswith("/steps/dataPoints")
    assert 'steps.interval.civil_start_time >= "2026-04-01T00:00:00"' in calls[0]["params"]["filter"]


def test_fetch_data_points_paginates(monkeypatch):
    page1 = _FakeResponse(json_body={"dataPoints": [{"n": 1}], "nextPageToken": "tok"})
    page2 = _FakeResponse(json_body={"dataPoints": [{"n": 2}]})
    client, calls = _client(monkeypatch, [page1, page2])
    points = list(client.fetch_data_points("steps", date(2026, 4, 1), date(2026, 4, 2)))
    assert points == [{"n": 1}, {"n": 2}]
    # Second request carries the page token.
    assert "pageToken" not in calls[0]["params"]
    assert calls[1]["params"]["pageToken"] == "tok"


def test_fetch_data_points_splits_multiple_days(monkeypatch):
    r1 = _FakeResponse(json_body={"dataPoints": [{"d": 1}]})
    r2 = _FakeResponse(json_body={"dataPoints": [{"d": 2}]})
    client, calls = _client(monkeypatch, [r1, r2])
    points = list(client.fetch_data_points("steps", date(2026, 4, 1), date(2026, 4, 3)))
    assert points == [{"d": 1}, {"d": 2}]
    assert len(calls) == 2  # one request per day chunk


def test_fetch_uses_kebab_endpoint_for_azm(monkeypatch):
    resp = _FakeResponse(json_body={"dataPoints": []})
    client, calls = _client(monkeypatch, [resp])
    list(client.fetch_data_points("active_zone_minutes", date(2026, 4, 1), date(2026, 4, 2)))
    assert calls[0]["url"].endswith("/active-zone-minutes/dataPoints")
    # filter uses the snake_case name, not the kebab endpoint name.
    assert "active_zone_minutes.interval" in calls[0]["params"]["filter"]


def test_fetch_retries_on_503_then_succeeds(monkeypatch):
    err = _FakeResponse(status_code=503, text="unavailable")
    ok = _FakeResponse(json_body={"dataPoints": [{"n": 1}]})
    client, calls = _client(monkeypatch, [err, ok])
    points = list(client.fetch_data_points("steps", date(2026, 4, 1), date(2026, 4, 2)))
    assert points == [{"n": 1}]
    assert len(calls) == 2  # retried once


def test_fetch_retries_on_429(monkeypatch):
    err = _FakeResponse(status_code=429, headers={"Retry-After": "1"})
    ok = _FakeResponse(json_body={"dataPoints": []})
    client, calls = _client(monkeypatch, [err, ok])
    list(client.fetch_data_points("steps", date(2026, 4, 1), date(2026, 4, 2)))
    assert len(calls) == 2


def test_fetch_raises_after_persistent_error(monkeypatch):
    from requests import HTTPError

    responses = [_FakeResponse(status_code=503, text="down") for _ in range(5)]
    client, _calls = _client(monkeypatch, responses)
    with pytest.raises(HTTPError):
        list(client.fetch_data_points("steps", date(2026, 4, 1), date(2026, 4, 2)))
