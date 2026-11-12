#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
source config/mirrors.env
set +a
if [[ "$(id -u)" != 0 ]]; then
  echo 'System package installation needs root on the cloud instance.' >&2
  exit 1
fi
source /etc/os-release
case "$ID" in
  debian)
    for file in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do
      [[ -f "$file" ]] || continue
      [[ -f "${file}.h3-backup" ]] || cp -p "$file" "${file}.h3-backup"
      sed -i \
        -e "s|https\?://deb.debian.org/debian-security|${APT_DEBIAN_SECURITY_MIRROR}|g" \
        -e "s|https\?://security.debian.org/debian-security|${APT_DEBIAN_SECURITY_MIRROR}|g" \
        -e "s|https\?://deb.debian.org/debian|${APT_DEBIAN_MIRROR}|g" "$file"
    done
    ;;
  ubuntu)
    for file in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do
      [[ -f "$file" ]] || continue
      [[ -f "${file}.h3-backup" ]] || cp -p "$file" "${file}.h3-backup"
      sed -i -E \
        -e 's|https?://([a-z]{2}\.)?archive.ubuntu.com/ubuntu/?|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' \
        -e 's|https?://security.ubuntu.com/ubuntu/?|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' "$file"
    done
    ;;
  *) echo "Unsupported OS: $ID" >&2; exit 1 ;;
esac
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  ca-certificates curl ffmpeg git libgl1 libgomp1 python3-venv tini
