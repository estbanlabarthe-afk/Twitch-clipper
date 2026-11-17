#!/bin/bash
# À lancer DANS Ubuntu (proot-distro), depuis le dossier Twitch-clipper :
#   bash termux/installer.sh
set -e
cd "$(dirname "$0")/.."
echo "== Paquets système (ffmpeg, python...) =="
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip ffmpeg git fonts-liberation > /dev/null
echo "== Environnement Python =="
python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
mkdir -p /sdcard/Movies/TwitchClipper 2>/dev/null || echo "!! /sdcard introuvable : as-tu lancé termux-setup-storage ?"
echo
echo "✓ Installation finie."
echo "Il reste : remplir .env (nano .env), puis quitter Ubuntu (exit) et suivre l'étape « Lancer » du README."
