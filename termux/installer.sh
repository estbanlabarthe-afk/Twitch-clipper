#!/bin/bash
# À lancer DANS Ubuntu (proot-distro), depuis le dossier Twitch-clipper :
#   bash termux/installer.sh
set -eo pipefail
cd "$(dirname "$0")/.."
echo "== Paquets système (ffmpeg, python...) =="
# pas de questions pendant l'installation (fuseau horaire = Paris)
export DEBIAN_FRONTEND=noninteractive TZ=Europe/Paris
ln -snf /usr/share/zoneinfo/Europe/Paris /etc/localtime 2>/dev/null || true
echo "Europe/Paris" > /etc/timezone
apt-get update -qq
echo "(1/2) environ 5 min, des lignes vont défiler..."
apt-get install -y python3 python3-venv python3-pip ffmpeg git fonts-liberation | grep -E "^(Reading package lists|Get|Setting up)" | cut -c1-60
echo "== Environnement Python =="
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
echo "(2/2) Whisper + OpenCV, environ 5-10 min..."
pip install -r requirements.txt | grep -E "^(Collecting|Requirement already|Successfully)"
[ -f .env ] || cp .env.example .env
mkdir -p /sdcard/Movies/TwitchClipper 2>/dev/null || echo "!! /sdcard introuvable : as-tu lancé termux-setup-storage ?"
echo
echo "✓ Installation finie."
echo "Il reste : remplir .env (nano .env), puis quitter Ubuntu (exit) et suivre l'étape « Lancer » du README."
