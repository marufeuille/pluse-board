"""Unit tests for ingest/oauth_bootstrap.py.

Only the pure/parsing logic is exercised; the interactive OAuth flow (browser,
local HTTP server, token exchange) is not run.
"""

from __future__ import annotations

import io

import oauth_bootstrap as m


def _make_handler(path):
    """Build a _CallbackHandler without running the socketserver machinery."""
    handler = m._CallbackHandler.__new__(m._CallbackHandler)
    handler.path = path
    handler.wfile = io.BytesIO()
    handler._responses = []
    handler.send_response = lambda code: handler._responses.append(code)
    handler.end_headers = lambda: None
    return handler


def test_callback_captures_auth_code(monkeypatch):
    monkeypatch.setattr(m, "auth_code", None, raising=False)
    handler = _make_handler("/callback?code=the-code&scope=x")
    handler.do_GET()
    assert m.auth_code == "the-code"
    assert handler._responses == [200]
    assert "認可完了".encode() in handler.wfile.getvalue()


def test_callback_without_code_sets_none(monkeypatch):
    monkeypatch.setattr(m, "auth_code", "stale", raising=False)
    handler = _make_handler("/callback")
    handler.do_GET()
    assert m.auth_code is None


def test_log_message_is_silenced(capsys):
    handler = m._CallbackHandler.__new__(m._CallbackHandler)
    handler.log_message("%s", "should-not-print")
    assert capsys.readouterr().out == ""


def test_constants_are_sensible():
    assert m.REDIRECT_URI == "http://localhost:8080/callback"
    assert m.SCOPES.startswith("https://www.googleapis.com/auth/")
