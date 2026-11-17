"""Détection automatique de la facecam dans un clip.

Principe :
1. on prend ~12 images réparties dans le clip ;
2. on cherche les visages : la facecam = un visage qui reste au même endroit
   (les persos du jeu, eux, bougent) ;
3. autour de ce visage, on cherche le cadre de la cam : des lignes droites qui
   restent fixes sur toutes les images (le jeu derrière change, pas le bord de la cam).
Renvoie la zone en fractions {x, y, l, h} ou None (pas de cam, ou cam plein écran).
"""
from pathlib import Path

import cv2
import numpy as np

NB_IMAGES = 12


def _images(video: Path, n: int = NB_IMAGES) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    images = []
    if total > 0:
        for k in range(n):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (0.05 + 0.9 * k / max(n - 1, 1))))
            ok, img = cap.read()
            if ok:
                images.append(img)
    cap.release()
    return images


def _visage_fixe(images: list[np.ndarray]):
    """(cx, cy, taille) du visage présent au même endroit sur le plus d'images."""
    h, w = images[0].shape[:2]
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    visages = []  # (n° image, cx, cy, taille)
    for i, img in enumerate(images):
        gris = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        mini = max(int(w * 0.025), 24)
        for (x, y, fw, fh) in casc.detectMultiScale(gris, 1.1, 5, minSize=(mini, mini)):
            visages.append((i, x + fw / 2, y + fh / 2, fw))

    meilleur, groupe = 0, []
    for (_, cx, cy, _) in visages:
        proches = [v for v in visages if abs(v[1] - cx) < 0.05 * w and abs(v[2] - cy) < 0.06 * h]
        nb = len({v[0] for v in proches})
        if nb > meilleur:
            meilleur, groupe = nb, proches
    if meilleur < max(3, int(len(images) * 0.4)):
        return None
    return (float(np.median([v[1] for v in groupe])),
            float(np.median([v[2] for v in groupe])),
            float(np.median([v[3] for v in groupe])))


def _bords_fixes(images: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Cartes des bords verticaux / horizontaux présents sur (presque) toutes les images.
    Un bord = saut de luminosité net entre deux pixels voisins (même faible contraste)."""
    vx, vy = [], []
    for img in images:
        g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (3, 3), 0)
        vx.append(np.abs(cv2.Sobel(g, cv2.CV_16S, 1, 0, ksize=3)) > 48)
        vy.append(np.abs(cv2.Sobel(g, cv2.CV_16S, 0, 1, ksize=3)) > 48)
    fx = (np.mean(vx, axis=0) >= 0.75).astype(np.uint8)
    fy = (np.mean(vy, axis=0) >= 0.75).astype(np.uint8)
    return (cv2.dilate(fx, np.ones((1, 3), np.uint8)) > 0,
            cv2.dilate(fy, np.ones((3, 1), np.uint8)) > 0)


def _chercher_bord(fixes, depart, fin, pas, segment, vertical) -> int | None:
    """Avance de `depart` vers `fin` ; renvoie la 1re ligne droite fixe trouvée."""
    a, b = segment
    for pos in range(int(depart), int(fin), pas):
        ligne = fixes[a:b, pos] if vertical else fixes[pos, a:b]
        if ligne.size and ligne.mean() > 0.6:
            return pos
    return None


def detecter(video: Path, apercu: Path | None = None) -> dict | None:
    images = _images(video)
    if len(images) < 3:
        return None
    h, w = images[0].shape[:2]
    visage = _visage_fixe(images)
    if not visage:
        return None
    cx, cy, t = visage
    if t > 0.13 * w:  # gros visage = caméra plein écran (Just Chatting) : pas de découpe
        return None

    fixes_v, fixes_h = _bords_fixes(images)
    lignes = (max(int(cy - 0.6 * t), 0), min(int(cy + 0.6 * t), h))
    colonnes = (max(int(cx - 0.6 * t), 0), min(int(cx + 0.6 * t), w))
    portee = 3.0 * t  # au-delà, on considère qu'il n'y a pas de cadre de ce côté

    g = _chercher_bord(fixes_v, cx - 0.55 * t, max(cx - portee, -1), -1, lignes, True)
    d = _chercher_bord(fixes_v, cx + 0.55 * t, min(cx + portee, w), 1, lignes, True)
    hh = _chercher_bord(fixes_h, cy - 0.55 * t, max(cy - portee, -1), -1, colonnes, False)
    b = _chercher_bord(fixes_h, cy + 0.55 * t, min(cy + portee, h), 1, colonnes, False)

    # pas de cadre trouvé : bord de l'image si proche, sinon marge autour du visage
    def defaut(val, bord_image, marge, sens):
        if val is not None:
            return val + 3 * sens  # on rentre de 3 px pour ne pas garder le liseré
        lim = bord_image
        return lim if abs(lim - marge) < 0.6 * t else marge

    x0 = defaut(g, 0, max(cx - 2.2 * t, 0), 1)
    x1 = defaut(d, w, min(cx + 2.2 * t, w), -1)
    y0 = defaut(hh, 0, max(cy - 1.6 * t, 0), 1)
    y1 = defaut(b, h, min(cy + 1.8 * t, h), -1)
    if x1 - x0 < t * 1.5 or y1 - y0 < t * 1.5:
        return None
    if (x1 - x0) * (y1 - y0) > 0.5 * w * h:  # trop grand : ce n'est pas une facecam
        return None

    zone = {"x": round(x0 / w, 4), "y": round(y0 / h, 4),
            "l": round((x1 - x0) / w, 4), "h": round((y1 - y0) / h, 4)}
    if apercu:
        img = images[len(images) // 2].copy()
        cv2.rectangle(img, (int(x0), int(y0)), (int(x1), int(y1)), (0, 255, 255), 4)
        apercu.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(apercu), img)
    return zone
