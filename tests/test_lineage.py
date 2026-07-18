"""Unit tests for ingest/lineage.py."""

from __future__ import annotations

import builtins
from datetime import datetime

import pytest

import lineage as m


# --------------------------------------------------------------------------- #
# _enabled
# --------------------------------------------------------------------------- #
def test_enabled_false_by_default(monkeypatch):
    monkeypatch.delenv("OPENLINEAGE_URL", raising=False)
    monkeypatch.delenv("OPENLINEAGE_DISABLED", raising=False)
    assert m._enabled() is False


def test_enabled_true_with_url(monkeypatch):
    monkeypatch.setenv("OPENLINEAGE_URL", "http://localhost:9000")
    monkeypatch.delenv("OPENLINEAGE_DISABLED", raising=False)
    assert m._enabled() is True


def test_enabled_false_when_disabled_flag(monkeypatch):
    monkeypatch.setenv("OPENLINEAGE_URL", "http://localhost:9000")
    monkeypatch.setenv("OPENLINEAGE_DISABLED", "TRUE")
    assert m._enabled() is False


# --------------------------------------------------------------------------- #
# _now
# --------------------------------------------------------------------------- #
def test_now_is_iso_utc():
    value = m._now()
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


# --------------------------------------------------------------------------- #
# track_ingest
# --------------------------------------------------------------------------- #
def test_track_ingest_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("OPENLINEAGE_URL", raising=False)
    ran = []
    with m.track_ingest("exercise", "proj", "ds", "tbl"):
        ran.append(True)
    assert ran == [True]


def test_track_ingest_yields_on_import_failure(monkeypatch, capsys):
    monkeypatch.setenv("OPENLINEAGE_URL", "http://localhost:9000")
    monkeypatch.delenv("OPENLINEAGE_DISABLED", raising=False)

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name.startswith("openlineage"):
            raise ImportError("no openlineage")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    ran = []
    with m.track_ingest("exercise", "proj", "ds", "tbl"):
        ran.append(True)
    assert ran == [True]  # body still runs despite lineage being unavailable
    assert "OpenLineage 無効化" in capsys.readouterr().out
