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
import shutil
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml

from clipper import telegram
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


def choisir_facecam(reglage, video: Path, apercu: Path | None = None):
    """reglage : "auto" (défaut) / "aucune" / {x, y, l, h}."""
    if isinstance(reglage, dict):
        return reglage
    if str(reglage).lower() in ("aucune", "non", "false", "none"):
        return None
    try:
        from clipper.facecam import detecter
    except ImportError:
        print("  ! opencv non installé : pas de détection de facecam")
        return None
    zone = detecter(video, apercu)
    if zone:
        print(f"  ✓ facecam détectée : {zone['x']},{zone['y']},{zone['l']},{zone['h']}")
    else:
        print("  · pas de facecam détectée : fond flouté")
    return zone


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
    # dossier des vidéos finies (ex: galerie du téléphone). Vide = à côté des bruts.
    final = os.environ.get("DOSSIER_FINAL") or cfg.get("dossier_final") or ""
    faits = lire_etat()
    ecrire_etat(faits)  # le fichier existe toujours (cache GitHub Actions)

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
                    fc = choisir_facecam(s.get("facecam", "auto"), brut,
                                         base / "bruts" / f"{nom}_facecam.jpg")
                    # montage dans le dossier du script (Android interdit les fichiers
                    # non vidéo dans Movies), puis on déplace juste la vidéo finie
                    sortie = monter(brut, base / f"{jour}_{nom}_9x16.mp4", cfg, fc, c["title"])
                    if final:
                        dest = Path(final) / u["login"]
                        dest.mkdir(parents=True, exist_ok=True)
                        sortie = Path(shutil.move(str(sortie), str(dest / sortie.name)))
                    if not cfg.get("garder_bruts", True):
                        brut.unlink(missing_ok=True)  # libère de la place
                    print(f"  ✓ monté : {sortie}")
                    if telegram.actif():
                        telegram.envoyer(sortie, f"🎬 {u['display_name']} : {c['title']}\n"
                                                 f"{c['view_count']} vues · {c['url']}")
                        print("  ✓ envoyé sur Telegram")
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
    p.add_argument("--titre", default="", help="titre affiché dans la bande (avec --fichier)")
    p.add_argument("--telegram-id", action="store_true",
                   help="affiche ton TELEGRAM_CHAT_ID (après avoir écrit à ton bot)")
    p.add_argument("--facecam", default="auto",
                   help="auto (défaut), aucune, ou zone x,y,l,h en fractions (ex: 0.75,0,0.25,0.28)")
    a = p.parse_args()

    charger_env()
    if a.telegram_id:
        telegram.afficher_chat_id()
        return
    cfg = yaml.safe_load((RACINE / a.config).read_text(encoding="utf-8"))
    if os.environ.get("WHISPER_MODELE"):  # ex: "base" sur GitHub Actions (plus rapide)
        cfg.setdefault("sous_titres", {})["modele_whisper"] = os.environ["WHISPER_MODELE"]
    if a.heures:
        cfg.setdefault("recuperation", {})["heures"] = a.heures

    if a.fichier:
        src = Path(a.fichier)
        reglage = a.facecam
        if "," in reglage:
            x, y, l, h = (float(v) for v in reglage.split(","))
            reglage = {"x": x, "y": y, "l": l, "h": h}
        fc = choisir_facecam(reglage, src, src.with_name(src.stem + "_facecam.jpg"))
        sortie = monter(src, src.with_name(src.stem + "_9x16.mp4"), cfg, fc, a.titre)
        print(f"✓ {sortie}")
        return

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
