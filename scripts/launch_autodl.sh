#!/usr/bin/env bash
# Use as the AutoDL instance's custom startup command after installation.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p .local
if [[ -f .local/server.pid ]]; then
  PID="$(cat .local/server.pid)"
  if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
    echo "A recorded server process still exists (PID $PID); inspect .local/server.log before starting another."
    exit 0
  fi
fi
nohup bash scripts/start.sh "$@" > .local/server.log 2>&1 &
echo "$!" > .local/server.pid
echo 'Cloud server launched; inspect .local/server.log and run scripts/doctor.py --server before treating it as ready.'
