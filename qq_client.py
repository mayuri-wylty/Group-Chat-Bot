from __future__ import annotations

import requests


class OneBotClient:
    def __init__(self, api_base: str, access_token: str = "", timeout: int = 10) -> None:
        self.api_base = api_base.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def call(self, action: str, payload: dict) -> dict:
        url = f"{self.api_base}/{action.lstrip('/')}"
        response = requests.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "ok" or data.get("retcode") not in (0, None):
            raise RuntimeError(f"OneBot API 返回异常：{data}")
        return data

    def send_private_msg(self, user_id: int | str, message: str) -> dict:
        return self.call(
            "send_private_msg",
            {
                "user_id": int(user_id),
                "message": message,
            },
        )

    def send_group_msg(self, group_id: int | str, message: str) -> dict:
        return self.call(
            "send_group_msg",
            {
                "group_id": int(group_id),
                "message": message,
            },
        )

    def get_login_info(self) -> dict:
        url = f"{self.api_base}/get_login_info"
        response = requests.post(
            url,
            json={},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
