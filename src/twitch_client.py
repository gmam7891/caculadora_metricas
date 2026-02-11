import time
import requests
from typing import Any, Dict, List, Optional

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_BASE = "https://api.twitch.tv/helix"

class TwitchClient:
    def __init__(self, client_id: str, client_secret: str, timeout: int = 20):
        if not client_id or not client_secret:
            raise ValueError("TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET são obrigatórios.")
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

        self._token: Optional[str] = None
        self._token_exp: float = 0.0
        self._session = requests.Session()

    def _get_app_token(self) -> str:
        now = time.time()
        if self._token and now < (self._token_exp - 60):
            return self._token

        r = self._session.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        j = r.json()
        self._token = j["access_token"]
        expires_in = int(j.get("expires_in", 3600))
        self._token_exp = now + expires_in
        return self._token

    def _headers(self) -> Dict[str, str]:
        token = self._get_app_token()
        return {"Client-Id": self.client_id, "Authorization": f"Bearer {token}"}

    def api_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{API_BASE}{path}"
        r = self._session.get(url, headers=self._headers(), params=params or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_users_by_logins(self, logins: List[str]) -> Dict[str, Dict[str, Any]]:
        if not logins:
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        chunk_size = 100
        for i in range(0, len(logins), chunk_size):
            chunk = logins[i:i + chunk_size]
            params = [("login", l) for l in chunk]
            r = self._session.get(
                f"{API_BASE}/users",
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            for u in data:
                out[u["login"].lower()] = u
        return out

    def get_streams_by_logins(self, logins: List[str]) -> Dict[str, Dict[str, Any]]:
        if not logins:
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        chunk_size = 100
        for i in range(0, len(logins), chunk_size):
            chunk = logins[i:i + chunk_size]
            params = [("user_login", l) for l in chunk]
            r = self._session.get(
                f"{API_BASE}/streams",
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            for s in data:
                out[s["user_login"].lower()] = s
        return out

    def get_vods_by_user_id(self, user_id: str, first: int = 20) -> List[Dict[str, Any]]:
        j = self.api_get(
            "/videos",
            params={"user_id": user_id, "first": min(max(int(first), 1), 100), "type": "archive"},
        )
        return j.get("data", [])
