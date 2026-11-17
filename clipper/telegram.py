"""Envoi des clips montés sur Telegram (bot gratuit)."""
import os
import subprocess
from pathlib import Path

import requests

LIMITE = 49 * 1024 * 1024  # l'API bot refuse les fichiers > 50 Mo


def actif() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _alleger(video: Path) -> Path:
    """Ré-encode plus léger si le fichier dépasse la limite Telegram."""
    leger = video.with_name(video.stem + "_tg.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video),
                    "-c:v", "libx264", "-crf", "26", "-maxrate", "5M", "-bufsize", "10M",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", str(leger)], check=True)
    return leger


def envoyer(video: Path, legende: str):
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    fichier = video if video.stat().st_size <= LIMITE else _alleger(video)
    with open(fichier, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendVideo", timeout=300,
                          data={"chat_id": chat, "caption": legende[:1000],
                                "supports_streaming": "true", "width": 1080, "height": 1920},
                          files={"video": (video.name, f, "video/mp4")})
    if not r.ok:
        raise RuntimeError(f"Telegram : {r.status_code} {r.text[:200]}")


def afficher_chat_id():
    """Aide : affiche l'ID de la conversation (envoie d'abord un message à ton bot)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Mets d'abord TELEGRAM_BOT_TOKEN dans .env")
        return
    data = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json()
    ids = {u["message"]["chat"]["id"] for u in data.get("result", []) if "message" in u}
    if ids:
        for i in ids:
            print(f"TELEGRAM_CHAT_ID={i}")
    else:
        print("Aucun message trouvé : envoie « salut » à ton bot sur Telegram, puis relance.")
