"""Transcription (faster-whisper) + génération d'un fichier .ass karaoké."""
from pathlib import Path


def transcrire(video: Path, modele: str = "small", langue: str = "fr") -> list[dict]:
    """Renvoie [{mot, debut, fin}, ...]. Liste vide si faster-whisper absent."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  ! faster-whisper non installé : pas de sous-titres")
        return []
    model = WhisperModel(modele, device="auto", compute_type="int8")
    segments, _ = model.transcribe(str(video), language=langue or None,
                                   word_timestamps=True, vad_filter=True)
    mots = []
    for seg in segments:
        for w in seg.words or []:
            texte = w.word.strip()
            if texte:
                mots.append({"mot": texte, "debut": w.start, "fin": w.end})
    return mots


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
