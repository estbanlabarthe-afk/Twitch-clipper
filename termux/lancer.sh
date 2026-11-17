#!/data/data/com.termux/files/usr/bin/bash
# À lancer dans TERMUX (pas dans Ubuntu) : bash ~/lancer.sh
# Garde le téléphone éveillé, met à jour le script, puis tourne en boucle.
termux-wake-lock 2>/dev/null || true
MINUTES="${1:-10}"
proot-distro login ubuntu -- bash -c "
  cd /root/Twitch-clipper || exit 1
  git pull -q || echo '(pas de mise à jour : pas de réseau ?)'
  . .venv/bin/activate
  export WHISPER_MODELE=base
  export DOSSIER_FINAL=/sdcard/Movies/TwitchClipper
  python main.py --boucle $MINUTES
"
