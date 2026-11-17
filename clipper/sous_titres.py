"""Transcription (faster-whisper) + génération d'un fichier .ass karaoké."""
import subprocess
from pathlib import Path


def _audio(video: Path):
    """Son du clip en 16 kHz mono (format attendu par Whisper), lu par ffmpeg.
    Évite PyAV, dont les nouvelles versions cassent faster-whisper."""
    import numpy as np
    brut = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(brut, np.int16).astype(np.float32) / 32768.0


def transcrire(video: Path, modele: str = "small", langue: str = "fr") -> list[dict]:
    """Renvoie [{mot, debut, fin, volume}, ...]. Liste vide si pas possible."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  ! faster-whisper non installé : pas de transcription")
        return []
    try:  # masque l'avertissement « GPU device discovery failed » (normal sur téléphone)
        import onnxruntime
        onnxruntime.set_default_logger_severity(3)
    except Exception:
        pass
    try:
        import numpy as np
        audio = _audio(video)
        if audio.size < 16000 // 2:  # moins d'une demi-seconde de son
            return []
        model = WhisperModel(modele, device="auto", compute_type="int8")
        segments, _ = model.transcribe(audio, language=langue or None,
                                       word_timestamps=True, vad_filter=True)
        mots = []
        for seg in segments:
            for w in seg.words or []:
                texte = w.word.strip()
                if texte:
                    morceau = audio[int(w.start * 16000):int(w.end * 16000)]
                    vol = float(np.sqrt(np.mean(morceau ** 2))) if morceau.size else 0.0
                    mots.append({"mot": texte, "debut": float(w.start),
                                 "fin": float(w.end), "volume": vol})
        return mots
    except Exception as e:
        print(f"  ! transcription impossible ({e})")
        return []


# Phrases que Whisper « invente » sur de la musique ou du silence
HALLUCINATIONS = ("amara", "sous-titr", "merci d'avoir regardé", "abonnez-vous",
                  "abonne-toi", "merci de votre attention", "à bientôt")


def phrases(mots: list[dict]) -> list[dict]:
    """Regroupe les mots en phrases (ponctuation ou pause > 0,8 s)."""
    res, cour = [], []
    for i, m in enumerate(mots):
        cour.append(m)
        fin_phrase = m["mot"][-1:] in ".!?…"
        pause = i + 1 < len(mots) and mots[i + 1]["debut"] - m["fin"] > 0.8
        if fin_phrase or pause or i == len(mots) - 1:
            res.append({"texte": " ".join(x["mot"] for x in cour).replace(" '", "'"),
                        "debut": cour[0]["debut"], "fin": cour[-1]["fin"],
                        "volume": max(x["volume"] for x in cour)})
            cour = []
    return res


def phrase_choc(mots: list[dict], max_mots: int = 12) -> str:
    """La phrase la plus marquante du clip : criée fort, exclamation/question,
    bonne longueur, plutôt vers la fin (le moment fort d'un clip est souvent là)."""
    liste = phrases(mots)
    if not liste:
        return ""
    vmax = max(p["volume"] for p in liste) or 1.0
    duree = liste[-1]["fin"] or 1.0
    meilleur, score_max = "", -99.0
    for p in liste:
        texte = p["texte"].strip(" ,")
        n = len(texte.split())
        if n < 3 or any(h in texte.lower() for h in HALLUCINATIONS):
            continue
        score = 3 * p["volume"] / vmax
        score += 1.5 if "!" in texte else 0
        score += 1.0 if "?" in texte else 0
        score += 1.0 if 4 <= n <= max_mots else (-2 if n > 18 else 0)
        score += 0.5 * p["debut"] / duree
        if score > score_max:
            meilleur, score_max = texte, score
    mots_titre = meilleur.split()
    if len(mots_titre) > max_mots:
        meilleur = " ".join(mots_titre[:max_mots]).rstrip(",;:") + "…"
    return meilleur.rstrip(".") if not meilleur.endswith("…") else meilleur


def _t(sec: float) -> str:
    sec = max(sec, 0)
    h, reste = divmod(sec, 3600)
    m, s = divmod(reste, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _propre(texte: str) -> str:
    return texte.replace("\\", "").replace("{", "(").replace("}", ")")


def _couleur_ass(hex_rgb: str) -> str:
    """'#FFD400' -> '&H0000D4FF&' (ASS = BGR)."""
    h = hex_rgb.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def ecrire_ass(mots: list[dict], sortie: Path, duree: float, cfg: dict,
               titre: str = "", titre_y: int = 0) -> Path:
    st = cfg.get("sous_titres", {})
    pub = cfg.get("mention_pub", "")
    taille = st.get("taille", 82)
    marge_bas = st.get("marge_bas", 520)
    actif = _couleur_ass(st.get("couleur_mot_actif", "#FFD400"))
    par_groupe = max(1, st.get("mots_par_ligne", 3))

    lignes = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,{st.get('police', 'Arial')},{taille},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        f"&H80000000,1,0,0,0,100,100,0,0,1,7,2,2,80,80,{marge_bas},1",
        "Style: Pub,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,1,0,0,0,"
        "100,100,0,0,3,10,0,8,60,60,170,1",
        f"Style: Titre,{st.get('police', 'Arial')},{cfg.get('titre', {}).get('taille', 58)},"
        "&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,0,5,60,60,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if titre:
        t = _propre(titre)
        if len(t) > 70:
            t = t[:67].rsplit(" ", 1)[0] + "…"
        lignes.append(f"Dialogue: 2,{_t(0)},{_t(duree)},Titre,,0,0,0,,{{\\an5\\pos(540,{titre_y})}}{t.upper()}")
    if pub:
        lignes.append(f"Dialogue: 1,{_t(0)},{_t(duree)},Pub,,0,0,0,,{_propre(pub)}")

    for g in range(0, len(mots), par_groupe):
        groupe = mots[g:g + par_groupe]
        for i, mot in enumerate(groupe):
            debut = mot["debut"]
            # le mot reste actif jusqu'au mot suivant (ou fin du groupe)
            fin = groupe[i + 1]["debut"] if i + 1 < len(groupe) else mot["fin"] + 0.15
            if g + par_groupe < len(mots):
                fin = min(fin, mots[g + par_groupe]["debut"])
            if fin <= debut:
                fin = debut + 0.05
            morceaux = []
            for j, autre in enumerate(groupe):
                t = _propre(autre["mot"]).upper()
                morceaux.append(f"{{\\c{actif}}}{t}{{\\c&H00FFFFFF&}}" if j == i else t)
            lignes.append(f"Dialogue: 0,{_t(debut)},{_t(fin)},Sub,,0,0,0,,{' '.join(morceaux)}")

    sortie.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return sortie
