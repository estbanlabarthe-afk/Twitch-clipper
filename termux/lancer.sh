#!/data/data/com.termux/files/usr/bin/bash
# À lancer dans TERMUX (pas dans Ubuntu) : bash ~/lancer.sh 2   (= toutes les 2 min)
# Garde le téléphone éveillé, met à jour le script, puis tourne en boucle.
termux-wake-lock 2>/dev/null || true
MINUTES="${1:-10}"
proot-distro login ubuntu -- bash -c "cd /root/Twitch-clipper && git pull -q" \
  || echo '(pas de mise à jour : pas de réseau ?)'

while true; do
  proot-distro login ubuntu -- bash -c '
    cd /root/Twitch-clipper || exit 1
    if [ ! -f .venv/bin/activate ]; then
      echo "✗ Installation pas faite. Tape : proot-distro login ubuntu   puis : bash /root/Twitch-clipper/termux/installer.sh"
      exit 1
    fi
    . .venv/bin/activate
    export WHISPER_MODELE=base DOSSIER_FINAL=/sdcard/Movies/TwitchClipper
    python main.py
  '
  # fait apparaître les clips tout de suite dans la Galerie (appli Termux:API)
  if command -v termux-media-scan >/dev/null; then
    termux-media-scan -r /sdcard/Download /sdcard/Movies/TwitchClipper >/dev/null 2>&1 \
      && echo "  ✓ galerie à jour"
  fi
  sleep $(( MINUTES * 60 ))
done
