# Twitch Clipper

Récupère automatiquement les clips Twitch les plus vus de tes streamers et les monte en **9:16 (1080x1920)**, prêts pour TikTok / YouTube Shorts :
- fond flouté **ou** facecam en haut + jeu en bas
- sous-titres karaoké automatiques (Whisper, en local, gratuit)
- mention « Partenariat rémunéré » (obligatoire sur clip.farm)
- format vérifié : H.264, 30 fps, AAC, faststart

> ⚠️ Ne clippe que des streamers qui ont une **campagne active** (clip.farm ou autre). Sinon, risque de droits d'auteur.

## Installation (Windows, une seule fois)

1. Installe **Python 3.11+** (coche « Add to PATH ») et **ffmpeg** :
   ```
   winget install Gyan.FFmpeg
   ```
2. Dans le dossier du projet :
   ```
   pip install -r requirements.txt
   ```
3. Crée une appli Twitch (gratuit) sur https://dev.twitch.tv/console/apps :
   - « Register Your Application », nom au choix, URL de redirection `http://localhost`, catégorie « Application Integration »
   - copie le **Client ID**, génère un **Client Secret**
4. Copie `.env.example` en `.env` et colle les deux valeurs.

## Utilisation

Mets tes streamers dans `config.yaml`, puis :

| Commande | Effet |
|---|---|
| `python main.py` | une passe : meilleurs clips des dernières 24 h |
| `python main.py --boucle 10` | relance toutes les 10 min (à laisser tourner pendant les lives) |
| `python main.py --streamer nom` | un seul streamer |
| `python main.py --heures 3` | seulement les clips des 3 dernières heures |
| `python main.py --sans-montage` | télécharge sans monter |
| `python main.py --fichier clip.mp4 --facecam 0.75,0,0.25,0.28` | monte un fichier local (pour régler la zone facecam) |

Résultat :
```
clips/<streamer>/<date>/
├── bruts/              ← clips originaux + infos (.json : titre, lien, vues…)
└── *_9x16.mp4          ← clips montés, prêts à poster
```
Les clips déjà traités sont notés dans `deja_faits.json` (pas de doublons).

## Régler la facecam

La zone se donne en fractions de l'image (0 à 1) : `x, y` = coin haut-gauche, `l, h` = largeur, hauteur.
Exemple : cam en haut à droite qui prend un quart de la largeur → `0.75, 0, 0.25, 0.28`.
Teste avec `--fichier`, puis copie la valeur dans `config.yaml` pour ce streamer.

## Notes
- Le 1er lancement avec sous-titres télécharge le modèle Whisper (~500 Mo pour `small`). Sur un PC lent, mets `base`.
- Les clips arrivent dans l'API Twitch quelques minutes après leur création.
