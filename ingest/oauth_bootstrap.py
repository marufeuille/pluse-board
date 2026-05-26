"""
Google Health API の OAuth 2.0 認可フローを実行して refresh token を取得する
ローカル専用ツール。取得した refresh token を GitHub Secrets に登録してください。

使い方:
    python oauth_bootstrap.py --client-id CLIENT_ID --client-secret CLIENT_SECRET
"""

import argparse
import http.server
import threading
import urllib.parse
import webbrowser
from urllib.request import urlopen, Request
from urllib.parse import urlencode
import json

SCOPES = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "http://localhost:8080/callback"

auth_code: str | None = None


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write("<p>認可完了。このタブを閉じてください。</p>".encode())

    def log_message(self, *_):
        pass


def _start_server():
    server = http.server.HTTPServer(("localhost", 8080), _CallbackHandler)
    server.handle_request()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    args = parser.parse_args()

    t = threading.Thread(target=_start_server, daemon=True)
    t.start()

    params = {
        "client_id": args.client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{AUTH_URI}?{urlencode(params)}"
    print(f"ブラウザで認可してください:\n{url}\n")
    webbrowser.open(url)
    t.join(timeout=120)

    if not auth_code:
        raise RuntimeError("認可コードを受け取れませんでした（120秒タイムアウト）")

    data = urlencode({
        "code": auth_code,
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = Request(TOKEN_URI, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urlopen(req) as resp:
        token = json.loads(resp.read())

    print("\n=== 取得した refresh token ===")
    print(token["refresh_token"])
    print("\nこの値を GitHub Secrets の GOOGLE_HEALTH_REFRESH_TOKEN に登録してください。")


if __name__ == "__main__":
    main()
