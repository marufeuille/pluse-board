"""
Google Health API の薄いラッパー。
エンドポイントのケース変換・OAuth refresh・ページネーションをここで吸収する。
API 仕様変更時はこのファイルだけ修正すれば良い。
"""

import os
import time
from datetime import date
from typing import Generator

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

BASE_URL = "https://health.googleapis.com/v4/users/me/dataTypes"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/googlehealth.activity_and_fitness"]

# エンドポイント URL は kebab-case、filter パラメータは snake_case
_ENDPOINT_NAME = {
    "exercise": "exercise",
    "steps": "steps",
    "active_zone_minutes": "active-zone-minutes",  # filter では snake_case で渡す
}

_FILTER_NAME = {
    "exercise": "exercise",
    "steps": "steps",
    "active_zone_minutes": "active_zone_minutes",
}


def _build_credentials() -> Credentials:
    return Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_HEALTH_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["GOOGLE_HEALTH_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_HEALTH_CLIENT_SECRET"],
        scopes=SCOPES,
    )


class HealthApiClient:
    def __init__(self) -> None:
        self._creds = _build_credentials()

    def _access_token(self) -> str:
        if not self._creds.valid:
            self._creds.refresh(GoogleRequest())
        return self._creds.token

    def fetch_data_points(
        self,
        data_type: str,
        start: date,
        end: date,
    ) -> Generator[dict, None, None]:
        """
        指定した data_type の dataPoint を全件 yield する。
        data_type: "exercise" | "steps" | "active_zone_minutes"
        """
        endpoint = _ENDPOINT_NAME[data_type]
        filter_key = _FILTER_NAME[data_type]
        url = f"{BASE_URL}/{endpoint}/dataPoints"
        filter_str = (
            f"{filter_key}.interval.civil_start_time >= \"{start}T00:00:00\" "
            f"AND {filter_key}.interval.civil_start_time < \"{end}T00:00:00\""
        )

        page_token: str | None = None
        while True:
            params: dict = {"filter": filter_str}
            if page_token:
                params["pageToken"] = page_token

            headers = {"Authorization": f"Bearer {self._access_token()}"}
            resp = requests.get(url, params=params, headers=headers, timeout=30)

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                time.sleep(retry_after)
                continue

            resp.raise_for_status()
            body = resp.json()

            for point in body.get("dataPoints", []):
                yield point

            page_token = body.get("nextPageToken")
            if not page_token:
                break
