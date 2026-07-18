"""Unit tests for sqlmesh_project/run_with_lineage.py."""

from __future__ import annotations

import pytest

import run_with_lineage as m


# --------------------------------------------------------------------------- #
# _lineage_enabled
# --------------------------------------------------------------------------- #
def test_lineage_enabled_false_by_default(monkeypatch):
    monkeypatch.delenv("OPENLINEAGE_URL", raising=False)
    monkeypatch.delenv("OPENLINEAGE_DISABLED", raising=False)
    assert m._lineage_enabled() is False


def test_lineage_enabled_true_with_url(monkeypatch):
    monkeypatch.setenv("OPENLINEAGE_URL", "http://localhost:9000")
    monkeypatch.delenv("OPENLINEAGE_DISABLED", raising=False)
    assert m._lineage_enabled() is True


def test_lineage_enabled_respects_disabled_flag(monkeypatch):
    monkeypatch.setenv("OPENLINEAGE_URL", "http://localhost:9000")
    monkeypatch.setenv("OPENLINEAGE_DISABLED", "true")
    assert m._lineage_enabled() is False


# --------------------------------------------------------------------------- #
# _strip_quotes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ('"proj"."ds"."tbl"', "proj.ds.tbl"),
        ("`proj`.`ds`.`tbl`", "proj.ds.tbl"),
        ("proj.ds.tbl", "proj.ds.tbl"),
        ('`proj`."ds".tbl', "proj.ds.tbl"),
    ],
)
def test_strip_quotes(raw, expected):
    assert m._strip_quotes(raw) == expected


# --------------------------------------------------------------------------- #
# main dispatch
# --------------------------------------------------------------------------- #
class _FakeCtx:
    def __init__(self):
        self.run_args = None
        self.plan_args = None

    def run(self, environment):
        self.run_args = environment

    def plan(self, environment, auto_apply=None, no_prompts=None):
        self.plan_args = (environment, auto_apply, no_prompts)


def test_main_run_dispatches_to_ctx_run(monkeypatch):
    ctx = _FakeCtx()
    monkeypatch.setattr(m, "_lineage_enabled", lambda: False)
    monkeypatch.setattr(m, "_context", lambda gateway: ctx)
    monkeypatch.setattr("sys.argv", ["prog", "run", "--gateway", "ci"])
    m.main()
    assert ctx.run_args is None  # default environment is prod (None)
    assert ctx.plan_args is None


def test_main_plan_dispatches_to_ctx_plan(monkeypatch):
    ctx = _FakeCtx()
    monkeypatch.setattr(m, "_lineage_enabled", lambda: False)
    monkeypatch.setattr(m, "_context", lambda gateway: ctx)
    monkeypatch.setattr("sys.argv", ["prog", "plan", "--environment", "dev_spike"])
    m.main()
    assert ctx.plan_args == ("dev_spike", True, True)


def test_install_lineage_console_is_best_effort(monkeypatch, capsys):
    # openlineage/sqlmesh_openlineage are not installed in the test env, so the
    # setup fails; it must be swallowed with a warning rather than raising.
    m._install_lineage_console()
    out = capsys.readouterr().out
    assert "OpenLineage" in out


def test_main_installs_console_when_enabled(monkeypatch):
    ctx = _FakeCtx()
    installed = []
    monkeypatch.setattr(m, "_lineage_enabled", lambda: True)
    monkeypatch.setattr(m, "_install_lineage_console", lambda: installed.append(True))
    monkeypatch.setattr(m, "_context", lambda gateway: ctx)
    monkeypatch.setattr("sys.argv", ["prog", "run"])
    m.main()
    assert installed == [True]
