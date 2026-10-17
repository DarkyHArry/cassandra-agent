#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
pkg-config --exists gtk4 libadwaita-1 libcurl || {
  echo "Dependências ausentes. Debian/Ubuntu:"
  echo "sudo apt install build-essential pkg-config libgtk-4-dev libadwaita-1-dev libcurl4-openssl-dev"
  exit 1
}
mkdir -p build
c++ -std=c++20 -O2 -Wall -Wextra desktop/dragon-desktop.cpp -o build/cassandra-security \
  $(pkg-config --cflags --libs gtk4 libadwaita-1 libcurl) -pthread
echo "Build concluído: $PWD/build/cassandra-security"
