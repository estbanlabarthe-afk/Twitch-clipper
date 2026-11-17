"""Accès à l'API officielle Twitch (Helix) + téléchargement des clips."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"


class Twitch:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None

    def _auth(self):
        r = requests.post(TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }, timeout=15)
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def _get(self, path: str, params: dict) -> dict:
        if not self.token:
            self._auth()
        for tentative in range(2):
            r = requests.get(API + path, params=params, timeout=15, headers={
                "Client-Id": self.client_id,
                "Authorization": f"Bearer {self.token}",
            })
            if r.status_code == 401 and tentative == 0:
                self._auth()  # jeton expiré : on en redemande un
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("Authentification Twitch impossible")

    def utilisateurs(self, logins: list[str]) -> dict[str, dict]:
        """login -> infos (id, display_name...)."""
        data = self._get("/users", {"login": [l.lower() for l in logins]})["data"]
        return {u["login"].lower(): u for u in data}

    def en_live(self, user_ids: list[str]) -> set[str]:
        data = self._get("/streams", {"user_id": user_ids, "type": "live"})["data"]
        return {s["user_id"] for s in data}

    def clips(self, broadcaster_id: str, heures: float, tri: str = "recents") -> list[dict]:
        """Clips créés ces X dernières heures, du plus récent au plus ancien (ou par vues)."""
        fin = datetime.now(timezone.utc)
        debut = fin - timedelta(hours=heures)
        iso = "%Y-%m-%dT%H:%M:%SZ"
        data = self._get("/clips", {
            "broadcaster_id": broadcaster_id,
            "started_at": debut.strftime(iso),
            "ended_at": fin.strftime(iso),
            "first": 100,
        })["data"]
        cle = "view_count" if tri == "vues" else "created_at"
        return sorted(data, key=lambda c: c[cle], reverse=True)


def telecharger(url: str, destination: Path) -> Path:
    """Télécharge un clip Twitch avec yt-dlp. Renvoie le chemin du .mp4."""
    import yt_dlp

    destination.parent.mkdir(parents=True, exist_ok=True)
    options = {
        "outtmpl": str(destination.with_suffix("")) + ".%(ext)s",
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info))
