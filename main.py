"""Twitch Clipper : récupère les clips Twitch les plus récents et les monte en 9:16.

Exemples :
  python main.py                       # une passe sur tous les streamers de config.yaml
  python main.py --boucle 10           # toutes les 10 min (à laisser tourner pendant les lives)
  python main.py --streamer squeezie   # un seul streamer
  python main.py --sans-montage        # télécharge seulement les clips bruts
  python main.py --fichier clip.mp4    # monte un fichier local (pour régler la facecam)
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml

from clipper.montage import monter
from clipper.twitch import Twitch, telecharger

RACINE = Path(__file__).parent
ETAT = RACINE / "deja_faits.json"


def charger_env():
    env = RACINE / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if "=" in ligne and not ligne.strip().startswith("#"):
                cle, val = ligne.split("=", 1)
                os.environ.setdefault(cle.strip(), val.strip().strip('"'))


def slug(texte: str, n: int = 40) -> str:
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:n] or "clip"


def lire_etat() -> set[str]:
    try:
        return set(json.loads(ETAT.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def ecrire_etat(faits: set[str]):
    ETAT.write_text(json.dumps(sorted(faits)), encoding="utf-8")


def normaliser_streamers(liste) -> list[dict]:
    """Accepte 'nom' ou {nom: ..., facecam: {...}}."""
    return [{"nom": s} if isinstance(s, str) else s for s in liste or []]


def une_passe(tw: Twitch, cfg: dict, seulement: str | None, montage: bool):
    streamers = normaliser_streamers(cfg["streamers"])
    if seulement:
        streamers = [s for s in streamers if s["nom"].lower() == seulement.lower()] \
            or [{"nom": seulement}]
    r = cfg.get("recuperation", {})
    dossier = RACINE / cfg.get("dossier_sortie", "clips")
    faits = lire_etat()

    infos = tw.utilisateurs([s["nom"] for s in streamers])
    for s in streamers:
        u = infos.get(s["nom"].lower())
        if not u:
            print(f"✗ {s['nom']} : introuvable sur Twitch")
            continue
        clips = tw.clips(u["id"], r.get("heures", 24), r.get("tri", "recents"))
        clips = [c for c in clips if c["view_count"] >= r.get("vues_min", 0)
                 and c["id"] not in faits][: r.get("max_par_streamer", 5)]
        print(f"→ {u['display_name']} : {len(clips)} nouveau(x) clip(s)")

        for c in clips:
            jour = c["created_at"][:10]
            heure = c["created_at"][11:16].replace(":", "h")
            nom = f"{heure}_{slug(c['title'])}_{c['id'][:8]}"
            base = dossier / u["login"] / jour
            try:
                brut = telecharger(c["url"], base / "bruts" / f"{nom}.mp4")
                (base / "bruts" / f"{nom}.json").write_text(json.dumps({
                    "titre": c["title"], "url": c["url"], "vues": c["view_count"],
                    "streamer": u["display_name"], "cree_par": c["creator_name"],
                    "date": c["created_at"], "duree": c["duration"],
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  ✓ téléchargé : {brut.name}")
                if montage:
                    sortie = monter(brut, base / f"{nom}_9x16.mp4", cfg, s.get("facecam"))
                    print(f"  ✓ monté : {sortie.relative_to(RACINE)}")
                faits.add(c["id"])
                ecrire_etat(faits)
            except Exception as e:  # un clip raté ne doit pas tout arrêter
                print(f"  ✗ {c['id']} : {e}")


def main():
    p = argparse.ArgumentParser(description="Récupère et monte des clips Twitch")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--streamer")
    p.add_argument("--heures", type=float, help="fenêtre de recherche (remplace la config)")
    p.add_argument("--boucle", type=float, metavar="MIN", help="relance toutes les MIN minutes")
    p.add_argument("--sans-montage", action="store_true")
    p.add_argument("--fichier", help="monte un fichier local au lieu d'aller sur Twitch")
    p.add_argument("--facecam", help="zone facecam x,y,l,h en fractions (ex: 0.75,0.7,0.25,0.3)")
    a = p.parse_args()

    cfg = yaml.safe_load((RACINE / a.config).read_text(encoding="utf-8"))
    if a.heures:
        cfg.setdefault("recuperation", {})["heures"] = a.heures

    if a.fichier:
        fc = None
        if a.facecam:
            x, y, l, h = (float(v) for v in a.facecam.split(","))
            fc = {"x": x, "y": y, "l": l, "h": h}
        src = Path(a.fichier)
        sortie = monter(src, src.with_name(src.stem + "_9x16.mp4"), cfg, fc)
        print(f"✓ {sortie}")
        return

    charger_env()
    cid, secret = os.environ.get("TWITCH_CLIENT_ID"), os.environ.get("TWITCH_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit("Il manque TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET dans .env (voir README)")
    tw = Twitch(cid, secret)

    while True:
        print(f"\n=== {datetime.now():%H:%M:%S} ===")
        try:
            une_passe(tw, cfg, a.streamer, not a.sans_montage)
        except Exception as e:
            print(f"✗ erreur : {e}")
        if not a.boucle:
            break
        time.sleep(a.boucle * 60)


if __name__ == "__main__":
    main()
