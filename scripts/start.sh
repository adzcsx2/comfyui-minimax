#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
set -a
source config/mirrors.env
[[ ! -f .env ]] || source .env
set +a
export COMFYUI_DIR="${COMFYUI_DIR:-$ROOT/runtime/ComfyUI}"
export VENV_DIR="${VENV_DIR:-$ROOT/runtime/venv}"
export MODEL_DIR="${MODEL_DIR:-/root/autodl-tmp/minimax-h3-models}"
export PUBLIC_MODEL_ROOTS="${PUBLIC_MODEL_ROOTS:-/.autodl:/root/autodl-pub}"
PY="$VENV_DIR/bin/python"
[[ -x "$PY" ]] || { echo 'Run scripts/install_autodl.sh first.' >&2; exit 1; }
mkdir -p "$COMFYUI_DIR/user/default/workflows"
if [[ ! -f "$COMFYUI_DIR/user/default/workflows/H3-Depth-Ref2VA-Union2.json" ]]; then
  cp workflows/h3-depth-ref2va.json "$COMFYUI_DIR/user/default/workflows/H3-Depth-Ref2VA-Union2.json"
fi
if [[ "${AUTO_DOWNLOAD_MODELS:-0}" == 1 ]]; then
  "$PY" scripts/download_models.py
else
  "$PY" scripts/download_models.py --link-only
fi
"$PY" scripts/doctor.py --require-cuda --require-models
exec "$PY" "$COMFYUI_DIR/main.py" --listen "${COMFYUI_LISTEN:-127.0.0.1}" \
  --port "${COMFYUI_PORT:-6006}" --preview-method none "$@"
