#!/usr/bin/env bash
# Run on the AutoDL Linux instance. Does not invoke Docker or modify the base ComfyUI.
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
export PIP_NO_CACHE_DIR=1
INSTALL_SYSTEM=0
DOWNLOAD_MODELS=0
for option in "$@"; do
  case "$option" in
    --install-system) INSTALL_SYSTEM=1 ;;
    --download-models) DOWNLOAD_MODELS=1 ;;
    *) echo "Unknown option: $option" >&2; exit 2 ;;
  esac
done
[[ "$INSTALL_SYSTEM" == 0 ]] || bash scripts/setup_apt.sh
PYTHON="${PYTHON_BIN:-python3.12}"
command -v "$PYTHON" >/dev/null || { echo 'Python 3.12 is required.' >&2; exit 1; }
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'
[[ "$(uname -m)" == x86_64 ]] || { echo 'This lockfile targets Linux x86_64.' >&2; exit 1; }
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV_DIR"
fi
PY="$VENV_DIR/bin/python"
"$PY" -m pip install --index-url "$PIP_INDEX_URL" --upgrade pip
"$PY" scripts/fetch_comfyui.py --destination "$COMFYUI_DIR"
"$PY" -m pip install --index-url "$PYTORCH_INDEX_URL" --extra-index-url "$PIP_INDEX_URL" \
  -r config/requirements-pytorch.txt
"$PY" -m pip install --index-url "$PIP_INDEX_URL" -c config/constraints.txt \
  -r "$COMFYUI_DIR/requirements.txt"
"$PY" -m pip check
mkdir -p "$COMFYUI_DIR/user/default/workflows" "$COMFYUI_DIR/input" "$COMFYUI_DIR/output" .local
cp -R custom_nodes/h3_control_guard "$COMFYUI_DIR/custom_nodes/"
cp workflows/h3-depth-ref2va.json "$COMFYUI_DIR/user/default/workflows/H3-Depth-Ref2VA-Union2.json"
"$PY" scripts/doctor.py --source-only
if [[ "$DOWNLOAD_MODELS" == 1 ]]; then
  "$PY" scripts/download_models.py
fi
"$PY" -m pip freeze > .local/installed-packages.txt
echo 'Cloud installation completed. Start with: bash scripts/start.sh'
