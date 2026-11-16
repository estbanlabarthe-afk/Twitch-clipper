# CLAUDE.md : Twitch Clipper

Projet perso d'Esteban, **séparé d'Esteb'Ant** (ne rien mélanger avec ce repo-là).

## But
Récupérer automatiquement les meilleurs clips Twitch de streamers en campagne (clip.farm), et les monter en 9:16 pour TikTok / Shorts. Esteban vérifie et poste à la main.

## Structure
- `main.py` : CLI (passe unique, `--boucle`, `--fichier`…)
- `clipper/twitch.py` : API Helix (client credentials) + téléchargement yt-dlp
- `clipper/montage.py` : ffmpeg, mises en page `flou` / `facecam`
- `clipper/sous_titres.py` : faster-whisper + fichier .ass karaoké + mention pub
- `config.yaml` : streamers, réglages ; `.env` : clés Twitch (jamais commitées)

## Règles
- Le script tourne sur le PC d'Esteban (Windows), **sans Claude** : pas de coût en tokens.
- Sortie : 1080x1920, 30 fps, H.264 yuv420p, AAC, faststart. Texte dans les zones de sécurité (150 px haut, 250 px bas).
- Mention « Partenariat rémunéré » obligatoire (règle clip.farm).
- Réponses en français informel, concises. Une commande terminal par bloc.

## Idées v2
- Détection des moments forts en live via le chat (pics de messages) + création de clips via l'API (scope `clips:edit`).
- Coupe auto des blancs, zoom sur les réactions.
