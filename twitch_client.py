import requests
from typing import Dict, List, Optional

class TwitchClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = self._get_access_token()

    def _get_access_token(self) -> str:
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        r = requests.post(url, params=params)
        r.raise_for_status()
        return r.json()["access_token"]

    def _headers(self):
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}"
        }

    def get_streams_by_logins(self, logins: List[str]) -> Dict[str, Dict]:
        """Divide em lotes de 80 canais (Twitch permite no máximo 100)"""
        if not logins:
            return {}

        result = {}
        batch_size = 80   # limite seguro

        for i in range(0, len(logins), batch_size):
            batch = logins[i:i + batch_size]
            url = "https://api.twitch.tv/helix/streams"
            params = [("user_login", login) for login in batch]

            try:
                r = requests.get(url, headers=self._headers(), params=params, timeout=10)
                r.raise_for_status()
                data = r.json()["data"]
                for s in data:
                    result[s["user_login"].lower()] = s
            except Exception as e:
                print(f"Erro em batch de streams: {e}")

        return result

    # (o resto das funções permanece igual)
    def get_users_by_logins(self, logins: List[str]) -> Dict[str, Dict]:
        if not logins:
            return {}
        url = "https://api.twitch.tv/helix/users"
        params = [("login", login) for login in logins]
        r = requests.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        data = r.json()["data"]
        return {u["login"].lower(): u for u in data}

    def get_vods_by_user_id(self, user_id: str, first: int = 20) -> List[Dict]:
        url = "https://api.twitch.tv/helix/videos"
        params = {"user_id": user_id, "first": first, "type": "archive"}
        r = requests.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        return r.json()["data"]