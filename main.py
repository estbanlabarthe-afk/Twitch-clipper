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


def lire_etat() -> dict:
    """{"ids": clips déjà traités, "moments": moments du live déjà montés}."""
    try:
        data = json.loads(ETAT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    if isinstance(data, list):  # ancien format : juste la liste des ids
        data = {"ids": data}
    return {"ids": set(data.get("ids", [])), "moments": data.get("moments", [])}


def ecrire_etat(etat: dict):
    ETAT.write_text(json.dumps({"ids": sorted(etat["ids"]),
                                "moments": etat["moments"][-3000:]}), encoding="utf-8")


def _date(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def moment(c: dict, streamer_id: str) -> dict:
    return {"s": streamer_id, "v": c.get("video_id") or "", "o": c.get("vod_offset"),
            "t": c["created_at"]}


def meme_moment(c: dict, streamer_id: str, moments: list[dict]) -> bool:
    """Vrai si ce clip montre le même moment du live qu'un clip déjà fait
    (plusieurs viewers qui clippent la même scène)."""
    m2 = moment(c, streamer_id)
    for m in moments:
        if m["s"] != streamer_id:
            continue
        if m["v"] and m["v"] == m2["v"] and m["o"] is not None and m2["o"] is not None:
            if abs(m["o"] - m2["o"]) < 30:  # même VOD, à 30 s près
                return True
            continue
        if abs((_date(m["t"]) - _date(m2["t"])).total_seconds()) < 45:  # créés quasi en même temps
            return True
    return False


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
    etat = lire_etat()
    faits = etat["ids"]
    ecrire_etat(etat)  # le fichier existe toujours (cache GitHub Actions)

    infos = tw.utilisateurs([s["nom"] for s in streamers])
    for s in streamers:
        u = infos.get(s["nom"].lower())
        if not u:
            print(f"✗ {s['nom']} : introuvable sur Twitch")
            continue
        tri = r.get("tri", "recents")
        clips = tw.clips(u["id"], r.get("heures", 24), tri)
        if r.get("heures", 24) > 3:
            # Twitch ne renvoie que les 100 plus vus de la période : on demande aussi
            # les 3 dernières heures à part, pour ne pas rater les clips tout neufs
            vus = {c["id"] for c in clips}
            clips += [c for c in tw.clips(u["id"], 3, tri) if c["id"] not in vus]
            cle = "view_count" if tri == "vues" else "created_at"
            clips.sort(key=lambda c: c[cle], reverse=True)
        # tes propres clips d'abord (ordre conservé à l'intérieur de chaque groupe)
        moi = {p.lower().strip() for p in str(cfg.get("mon_pseudo") or "").split(",") if p.strip()}
        a_moi = lambda c: (c.get("creator_name") or "").lower() in moi
        clips.sort(key=lambda c: not a_moi(c))
        choisis, doublons = [], 0
        for c in clips:
            if c["id"] in faits:
                continue
            if a_moi(c):  # ton clip : jamais filtré (vues, doublon)
                choisis.append(c)
                continue
            if c["view_count"] < r.get("vues_min", 0):
                continue
            if meme_moment(c, u["id"], etat["moments"] + [moment(x, u["id"]) for x in choisis]):
                faits.add(c["id"])  # doublon : on le note pour ne plus jamais le regarder
                doublons += 1
                continue
            choisis.append(c)
            if len(choisis) >= r.get("max_par_streamer", 5):
                break  # (tes clips passent même au-delà de cette limite)
        ecrire_etat(etat)
        clips = choisis
        print(f"→ {u['display_name']} : {len(clips)} nouveau(x) clip(s)")
        if doublons:
            print(f"  · {doublons} doublon(s) ignoré(s) (même moment déjà clippé)")

        for c in clips:
            traiter(c, u, s, cfg, etat, montage, a_moi(c))


def traiter(c: dict, u: dict, s: dict, cfg: dict, etat: dict, montage: bool = True,
            a_moi: bool = False) -> Path | None:
    """Télécharge + monte un clip, range la vidéo, met à jour la mémoire."""
    dossier = RACINE / cfg.get("dossier_sortie", "clips")
    # dossier des vidéos finies (ex: galerie du téléphone). Vide = à côté des bruts.
    final = os.environ.get("DOSSIER_FINAL") or cfg.get("dossier_final") or ""
    jour = c["created_at"][:10]
    heure = c["created_at"][11:16].replace(":", "h")
    nom = f"{'MOI_' if a_moi else ''}{heure}_{slug(c['title'])}_{c['id'][:8]}"
    if a_moi:
        print(f"  ⭐ ton clip : {c['title']}")
    base = dossier / u["login"] / jour
    try:
        brut = telecharger(c["url"], base / "bruts" / f"{nom}.mp4")
        (base / "bruts" / f"{nom}.json").write_text(json.dumps({
            "titre": c["title"], "url": c["url"], "vues": c["view_count"],
            "streamer": u["display_name"], "cree_par": c["creator_name"],
            "date": c["created_at"], "duree": c["duration"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ téléchargé : {brut.name}")
        sortie = None
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
        etat["ids"].add(c["id"])
        etat["moments"].append(moment(c, u["id"]))
        ecrire_etat(etat)
        return sortie
    except Exception as e:  # un clip raté ne doit pas tout arrêter
        print(f"  ✗ {c['id']} : {e}")
        return None


LIEN_CLIP = re.compile(r"(?:clips\.twitch\.tv/(?:embed\?clip=)?|twitch\.tv/[^/\s]+/clip/)([A-Za-z0-9_-]+)")


def depuis_liens(tw: Twitch, cfg: dict, textes: list[str], forcer: bool = False):
    """Monte uniquement les clips dont on donne le lien (texte partagé, URL...)."""
    ids = []
    for texte in textes:
        for slug_clip in LIEN_CLIP.findall(texte):
            if slug_clip not in ids:
                ids.append(slug_clip)
    if not ids:
        print("✗ Aucun lien de clip Twitch reconnu dans :", " ".join(textes)[:200])
        return
    etat = lire_etat()
    clips = tw.clips_par_id(ids)
    trouves = {c["id"] for c in clips}
    for i in ids:
        if i not in trouves:
            print(f"✗ clip introuvable (supprimé ou lien faux) : {i}")
    if not clips:
        return
    users = tw.utilisateurs_par_id(list({c["broadcaster_id"] for c in clips}))
    reglages = {s["nom"].lower(): s for s in normaliser_streamers(cfg.get("streamers"))}
    moi = {p.lower().strip() for p in str(cfg.get("mon_pseudo") or "").split(",") if p.strip()}
    for n, c in enumerate(clips, 1):
        u = users.get(c["broadcaster_id"]) or {"id": c["broadcaster_id"],
                                               "login": slug(c["broadcaster_name"]),
                                               "display_name": c["broadcaster_name"]}
        print(f"→ [{n}/{len(clips)}] {u['display_name']} : {c['title']}")
        if c["id"] in etat["ids"] and not forcer:
            print("  · déjà monté avant (ajoute --forcer pour le refaire)")
            continue
        traiter(c, u, reglages.get(u["login"].lower(), {}), cfg, etat, True,
                (c.get("creator_name") or "").lower() in moi)


def main():
    p = argparse.ArgumentParser(description="Récupère et monte des clips Twitch")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--streamer")
    p.add_argument("--heures", type=float, help="fenêtre de recherche (remplace la config)")
    p.add_argument("--boucle", type=float, metavar="MIN", help="relance toutes les MIN minutes")
    p.add_argument("--sans-montage", action="store_true")
    p.add_argument("--fichier", help="monte un fichier local au lieu d'aller sur Twitch")
    p.add_argument("--lien", nargs="+", metavar="LIEN",
                   help="monte seulement ces clips (liens Twitch, ou texte partagé qui en contient)")
    p.add_argument("--forcer", action="store_true", help="avec --lien : refait même si déjà monté")
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

    if a.lien:
        depuis_liens(tw, cfg, a.lien, a.forcer)
        return

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
