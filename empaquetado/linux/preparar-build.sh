#!/usr/bin/env bash
# Instala en la máquina de construcción (Ubuntu 22.04) las bibliotecas de sistema que Qt necesita
# para ejecutar la suite en modo offscreen y para que `ldd` resuelva el congelado (calcular y
# comprobar Depends). Requiere sudo: úselo solo dentro de la MV de construcción.
# Uso: empaquetado/linux/preparar-build.sh
set -euo pipefail

PAQUETES=(
    binutils libegl1 libgl1 libglib2.0-0 libdbus-1-3 libfontconfig1 libfreetype6 libxkbcommon0
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
    libxcb-render-util0 libxcb-shape0 libxcb-util1 libxcb-xkb1 desktop-file-utils
    xvfb xauth dbus-x11 gnome-keyring
)
sudo -n apt-get update -qq
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${PAQUETES[@]}"
echo "[preparar-build] bibliotecas de construcción instaladas"
