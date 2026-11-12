#!/usr/bin/env bash
# Preserve the verified base panel, then start our independent ComfyUI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/root/miniconda3/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
BASE_START=/root/zealman-app/scripts/improved-autostart.sh
if [[ -r "$BASE_START" ]]; then
  if ! bash "$BASE_START"; then
    echo 'Base panel startup failed; its log is /tmp/zealman-app-improved-autostart.log' >&2
  fi
fi
exec bash "$ROOT/scripts/launch_autodl.sh" "$@"
