"""Montage 9:16 (1080x1920) avec ffmpeg, prêt pour TikTok / Shorts."""
import json
import subprocess
from pathlib import Path

from .sous_titres import ecrire_ass, transcrire

L, H = 1080, 1920


def sonder(video: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    s = data["streams"][0]
    return {"w": s["width"], "h": s["height"], "duree": float(data["format"]["duration"])}


def _couleur_ff(hex_rgb: str) -> str:
    return "0x" + hex_rgb.lstrip("#")


def _filtre_flou(info: dict, barre: int, couleur: str) -> tuple[str, int]:
    """Vidéo entière au centre, même vidéo floutée en fond.
    Bande titre (si barre > 0) collée juste au-dessus de la vidéo."""
    haut_video = round(L * info["h"] / info["w"] / 2) * 2
    y_video = (H - haut_video) // 2
    y_barre = max(y_video - barre, 0)
    f = (f"[0:v]scale={L}:{H}:force_original_aspect_ratio=increase,crop={L}:{H},"
         f"boxblur=20:2,eq=brightness=-0.08[fond];"
         f"[0:v]scale={L}:{haut_video}[avant];"
         f"[fond][avant]overlay=0:{y_video}")
    if barre:
        f += f",drawbox=x=0:y={y_barre}:w={L}:h={barre}:color={couleur}@1:t=fill"
    return f + ",setsar=1[v]", y_barre + barre // 2


def _filtre_facecam(fc: dict, haut_cam: int, barre: int, couleur: str) -> tuple[str, int]:
    """Facecam en haut, bande titre, jeu (centre de l'image) en bas.
    fc = zone de la facecam en fraction de l'image source : x, y, l, h (0 à 1)."""
    haut_jeu = H - haut_cam - barre
    return (f"[0:v]split=2[a][b];"
            f"[a]crop=iw*{fc['l']}:ih*{fc['h']}:iw*{fc['x']}:ih*{fc['y']},"
            f"scale={L}:{haut_cam}:force_original_aspect_ratio=increase,crop={L}:{haut_cam},"
            f"pad={L}:{haut_cam + barre}:0:0:color={couleur}[cam];"
            f"[b]crop=min(iw\\,ih*{L}/{haut_jeu}):ih,"
            f"scale={L}:{haut_jeu}:force_original_aspect_ratio=increase,crop={L}:{haut_jeu}[jeu];"
            f"[cam][jeu]vstack=inputs=2,setsar=1[v]"), haut_cam + barre // 2


def monter(source: Path, sortie: Path, cfg: dict, facecam: dict | None = None,
           titre: str = "") -> Path:
    m = cfg.get("montage", {})
    tc = cfg.get("titre", {})
    info = sonder(source)
    duree = min(info["duree"], float(m.get("duree_max", 60)))

    titre = titre.strip() if tc.get("actif", True) else ""
    barre = int(tc.get("hauteur", 170)) if titre else 0
    couleur = _couleur_ff(tc.get("couleur_fond", "#7B2FF7"))
    if facecam:
        filtre, titre_y = _filtre_facecam(facecam, int(m.get("hauteur_facecam", 620)), barre, couleur)
    else:
        filtre, titre_y = _filtre_flou(info, barre, couleur)

    # sous-titres + mention pub (fichier .ass à côté de la sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    ass = None
    mots = []
    if cfg.get("sous_titres", {}).get("actif", True):
        st = cfg["sous_titres"]
        print("  … transcription")
        mots = transcrire(source, st.get("modele_whisper", "small"), st.get("langue", "fr"))
    if mots or titre or cfg.get("mention_pub"):
        ass = ecrire_ass(mots, sortie.with_suffix(".ass"), duree, cfg, titre, titre_y)
        # chemin relatif + cwd : évite les soucis de "C:\" dans le filtre sous Windows
        filtre = filtre.replace("[v]", "[v0]") + f";[v0]subtitles={ass.name}[v]"

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source.resolve()), "-t", f"{duree:.2f}",
        "-filter_complex", filtre, "-map", "[v]", "-map", "0:a?",
        "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-maxrate", "10M", "-bufsize", "20M", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", str(sortie.resolve()),
    ]
    subprocess.run(cmd, check=True, cwd=sortie.parent)
    if ass and not m.get("garder_ass", False):
        ass.unlink(missing_ok=True)
    return sortie
