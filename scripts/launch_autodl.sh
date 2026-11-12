#!/usr/bin/env bash
# Use as the AutoDL instance's custom startup command after installation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p .local
[[ ! -f .env ]] || source .env
COMFYUI_DIR="${COMFYUI_DIR:-$ROOT/runtime/ComfyUI}"
exec 8>.local/launch.lock
if ! flock -n 8; then
  echo 'Another launcher is recording the server process; no second server was started.'
  exit 0
fi
if [[ -f .local/server.pid ]]; then
  PID="$(cat .local/server.pid)"
  if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
    [[ -r "/proc/$PID/cmdline" ]] || { echo 'Cannot verify the recorded live PID.' >&2; exit 1; }
    if grep -Fzxq -- "$COMFYUI_DIR/main.py" "/proc/$PID/cmdline" || \
       grep -Fzxq -- "$ROOT/scripts/start.sh" "/proc/$PID/cmdline"; then
      echo "The configured server or its startup process already exists (PID $PID)."
      exit 0
    fi
    echo 'Recorded PID belongs to another command; starting the configured server.'
  fi
fi
nohup bash "$ROOT/scripts/start.sh" "$@" 8>&- > .local/server.log 2>&1 &
echo "$!" > .local/server.pid
echo 'Cloud server launched; inspect .local/server.log and run scripts/doctor.py --server before treating it as ready.'
