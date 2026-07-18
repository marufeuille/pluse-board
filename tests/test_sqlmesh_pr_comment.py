"""Unit tests for scripts/sqlmesh_pr_comment.py.

The SQLMesh ``Context`` is only imported inside ``main`` for the model-change
path, so every helper below is exercised without a real SQLMesh project.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

import sqlmesh_pr_comment as m


# --------------------------------------------------------------------------- #
# _env
# --------------------------------------------------------------------------- #
def test_env_strips_whitespace(monkeypatch):
    monkeypatch.setenv("FOO", "  bar \n")
    assert m._env("FOO") == "bar"


def test_env_default_when_unset(monkeypatch):
    monkeypatch.delenv("MISSING", raising=False)
    assert m._env("MISSING", "fallback") == "fallback"
    assert m._env("MISSING") == ""


# --------------------------------------------------------------------------- #
# _api
# --------------------------------------------------------------------------- #
def test_api_get_sets_headers_and_parses_json(monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"ok": True}).encode()

    def _fake_urlopen(req):
        captured["req"] = req
        return _Resp()

    monkeypatch.setattr(m.urllib.request, "urlopen", _fake_urlopen)
    out = m._api("GET", "https://api/x", "tok")
    assert out == {"ok": True}
    req = captured["req"]
    assert req.get_header("Authorization") == "Bearer tok"
    assert req.get_method() == "GET"
    assert req.data is None


def test_api_post_encodes_body(monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def _fake_urlopen(req):
        captured["req"] = req
        return _Resp()

    monkeypatch.setattr(m.urllib.request, "urlopen", _fake_urlopen)
    m._api("POST", "https://api/x", "tok", {"body": "hi"})
    req = captured["req"]
    assert req.get_method() == "POST"
    assert json.loads(req.data.decode()) == {"body": "hi"}
    assert req.get_header("Content-type") == "application/json"


# --------------------------------------------------------------------------- #
# changed_model_files
# --------------------------------------------------------------------------- #
def test_changed_model_files_from_env(monkeypatch):
    monkeypatch.setenv(
        "CHANGED_FILES",
        "sqlmesh_project/models/mart_a.sql sqlmesh_project/models/mart_b.sql "
        "README.md sqlmesh_project/audits/x.sql",
    )
    files = m.changed_model_files("owner/repo", "1", "tok", "sqlmesh_project")
    assert files == [
        "sqlmesh_project/models/mart_a.sql",
        "sqlmesh_project/models/mart_b.sql",
    ]


def test_changed_model_files_from_api_paginates(monkeypatch):
    monkeypatch.delenv("CHANGED_FILES", raising=False)
    page1 = [{"filename": f"sqlmesh_project/models/m{i}.sql"} for i in range(100)]
    page2 = [
        {"filename": "sqlmesh_project/models/last.sql"},
        {"filename": "docs/readme.md"},
    ]
    calls = []

    def _fake_api(method, url, token, body=None):
        calls.append(url)
        return page1 if url.endswith("page=1") else page2

    monkeypatch.setattr(m, "_api", _fake_api)
    files = m.changed_model_files("owner/repo", "1", "tok", "sqlmesh_project")
    assert len(files) == 101  # 100 from page 1 + 1 model from page 2
    assert "docs/readme.md" not in files
    assert len(calls) == 2  # stopped after a short page


# --------------------------------------------------------------------------- #
# build_lineage / mermaid
# --------------------------------------------------------------------------- #
def _fake_ctx():
    graph = {
        "raw": set(),
        "stg": {"raw"},
        "mart": {"stg"},
        "unrelated": set(),
    }
    models = {
        fqn: SimpleNamespace(view_name=fqn.upper()) for fqn in graph
    }
    return SimpleNamespace(dag=SimpleNamespace(graph=graph), models=models)


def test_build_lineage_includes_ancestors_and_descendants():
    ctx = _fake_ctx()
    nodes, edges = m.build_lineage(ctx, {"stg"})
    assert nodes == {"raw", "stg", "mart"}
    assert "unrelated" not in nodes
    assert set(edges) == {("raw", "stg"), ("stg", "mart")}


def test_mermaid_renders_nodes_edges_and_highlights_changed():
    ctx = _fake_ctx()
    nodes = {"raw", "stg", "mart"}
    edges = [("raw", "stg"), ("stg", "mart")]
    out = m.mermaid(ctx, nodes, edges, {"stg"})
    assert out.startswith("```mermaid")
    assert "flowchart LR" in out
    assert '"STG"' in out  # uses view_name as label
    assert "-->" in out
    assert "classDef changed" in out


# --------------------------------------------------------------------------- #
# bq_table_url
# --------------------------------------------------------------------------- #
def test_bq_table_url():
    url = m.bq_table_url("proj", "fitbit_mart", "mart_steps_daily")
    assert url.startswith("https://console.cloud.google.com/bigquery?project=proj")
    assert "1sproj" in url
    assert "2sfitbit_mart" in url
    assert "3smart_steps_daily" in url


# --------------------------------------------------------------------------- #
# check_links
# --------------------------------------------------------------------------- #
def test_check_links_filters_and_sorts(monkeypatch):
    runs = {
        "check_runs": [
            {"name": "SQLMesh - mart_b", "html_url": "u2"},
            {"name": "SQLMesh - mart_a", "html_url": "u1"},
            {"name": "Other check", "html_url": "u3"},
        ]
    }
    monkeypatch.setattr(m, "_api", lambda *a, **k: runs)
    out = m.check_links("owner/repo", "abc123", "tok")
    assert out == [("SQLMesh - mart_a", "u1"), ("SQLMesh - mart_b", "u2")]


def test_check_links_empty_sha():
    assert m.check_links("owner/repo", "", "tok") == []


# --------------------------------------------------------------------------- #
# upsert_comment
# --------------------------------------------------------------------------- #
def test_upsert_comment_creates_new(monkeypatch):
    calls = []

    def _fake_api(method, url, token, body=None):
        calls.append((method, url, body))
        if method == "GET":
            return []  # no existing comments
        return {}

    monkeypatch.setattr(m, "_api", _fake_api)
    m.upsert_comment("owner/repo", "5", "tok", "hello")
    methods = [c[0] for c in calls]
    assert "POST" in methods
    assert "PATCH" not in methods


def test_upsert_comment_updates_existing(monkeypatch):
    calls = []

    def _fake_api(method, url, token, body=None):
        calls.append((method, url, body))
        if method == "GET":
            return [{"id": 42, "body": f"{m.MARKER}\nold"}]
        return {}

    monkeypatch.setattr(m, "_api", _fake_api)
    m.upsert_comment("owner/repo", "5", "tok", "new body")
    patch_calls = [c for c in calls if c[0] == "PATCH"]
    assert len(patch_calls) == 1
    assert "comments/42" in patch_calls[0][1]
    assert patch_calls[0][2] == {"body": "new body"}


# --------------------------------------------------------------------------- #
# main (no model changes branch)
# --------------------------------------------------------------------------- #
def test_main_no_models_dry_run(monkeypatch, capsys):
    monkeypatch.setenv("CHANGED_FILES", "README.md docs/x.md")
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("PR_NUMBER", "5")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    rc = m.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert m.MARKER in out
    assert "モデル変更はありません" in out
