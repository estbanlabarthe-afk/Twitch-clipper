# Twitch Clipper

Récupère automatiquement les clips Twitch les plus récents de tes streamers et les monte en **9:16 (1080x1920)**, prêts pour TikTok / YouTube Shorts :
- facecam en haut, **bande violette avec le titre du clip**, jeu en bas (ou fond flouté si pas de facecam réglée)
- sous-titres karaoké automatiques (Whisper, en local, gratuit)
- texte optionnel en haut de la vidéo (`mention_pub` dans `config.yaml`)
- format vérifié : H.264, 30 fps, AAC, faststart

> ⚠️ Les clips restent le contenu des streamers : demande-leur l'accord avant de reposter, sinon risque de signalement pour droits d'auteur.

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

## Mode automatique 24h/24 (gratuit) ⭐

Le script tourne tout seul **sur les serveurs de GitHub, toutes les 2 h**, et t'envoie les clips montés **sur Telegram**. Pas besoin de laisser ton PC allumé.

**1. Créer ton bot Telegram (2 min)**
- Sur Telegram, écris à **@BotFather** → `/newbot` → choisis un nom → il te donne un **token**.
- Écris « salut » à ton nouveau bot.
- Sur ton PC, mets le token dans `.env` (`TELEGRAM_BOT_TOKEN=...`) puis :
  ```
  python main.py --telegram-id
  ```
  → il affiche ton `TELEGRAM_CHAT_ID`.

**2. Donner les clés à GitHub**
Sur github.com, dans ton repo : **Settings → Secrets and variables → Actions → New repository secret**, et ajoute ces 4 secrets :
`TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

**3. Lancer**
Onglet **Actions → Clipper auto → Run workflow** pour un 1er essai. Ensuite ça tourne tout seul.
Pour changer les streamers : modifie `config.yaml` directement sur github.com.

**Coût** : 0 €. Le repo privé a 2000 min/mois gratuites ; une passe sans clip ≈ 1 min, un clip ≈ 1-2 min. Avec 5 clips max par passe toutes les 2 h, ça tient. Suivi : Settings → Billing → Usage.
Si tu dépasses, GitHub met juste en pause jusqu'au mois suivant (pas de facture, sauf si tu as ajouté un moyen de paiement + un budget).

## Utilisation sur ton PC

Mets tes streamers dans `config.yaml`, puis :

| Commande | Effet |
|---|---|
| `python main.py` | une passe : les 5 clips les plus récents (24 h max) |
| `python main.py --boucle 10` | relance toutes les 10 min (à laisser tourner pendant les lives) |
| `python main.py --streamer nom` | un seul streamer |
| `python main.py --heures 3` | seulement les clips des 3 dernières heures |
| `python main.py --sans-montage` | télécharge sans monter |
| `python main.py --fichier clip.mp4 --facecam 0.75,0,0.25,0.28 --titre "Mon titre"` | monte un fichier local (pour régler la zone facecam) |

Résultat :
```
clips/<streamer>/<date>/
├── bruts/              ← clips originaux + infos (.json : titre, lien, vues…)
└── *_9x16.mp4          ← clips montés, prêts à poster
```
Les clips déjà traités sont notés dans `deja_faits.json` (pas de doublons).

## Facecam automatique

Pour chaque clip, le script **trouve la cam tout seul** : il cherche un visage qui reste au même endroit, puis le cadre fixe autour.
- Aperçu de ce qu'il a trouvé : `bruts/<clip>_facecam.jpg` (rectangle jaune).
- Pas de cam trouvée (ou cam plein écran) → mise en page fond flouté.
- Limites : visage de profil ou caché, cam sans bord net sur un jeu très statique. Dans ce cas, règle-la à la main (ci-dessous).

## Régler la facecam à la main

La zone se donne en fractions de l'image (0 à 1) : `x, y` = coin haut-gauche, `l, h` = largeur, hauteur.
Exemple : cam en haut à droite qui prend un quart de la largeur → `0.75, 0, 0.25, 0.28`.
Teste avec `--fichier`, puis copie la valeur dans `config.yaml` pour ce streamer.

## Notes
- Le 1er lancement avec sous-titres télécharge le modèle Whisper (~500 Mo pour `small`). Sur un PC lent, mets `base`.
- Les clips arrivent dans l'API Twitch quelques minutes après leur création.
