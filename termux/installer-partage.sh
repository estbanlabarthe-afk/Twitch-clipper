#!/data/data/com.termux/files/usr/bin/bash
# À lancer dans TERMUX (pas Ubuntu), une seule fois :
#   proot-distro login ubuntu -- cat /root/Twitch-clipper/termux/installer-partage.sh > ~/p.sh ; bash ~/p.sh
set -e
mkdir -p ~/bin
for f in termux-url-opener termux-file-editor; do
  proot-distro login ubuntu -- cat /root/Twitch-clipper/termux/$f > ~/bin/$f
  chmod +x ~/bin/$f
done
echo "✓ Partage installé. Dans l'appli Twitch : clip > Partager > Termux."
