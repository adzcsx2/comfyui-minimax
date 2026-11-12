"""Report separate source, model, CUDA and live-node checks. Never claim a visual quality pass."""

from __future__ import annotations

import argparse
import json
import re
import struct
import urllib.request
from pathlib import Path

from common import ROOT, read_json, settings

REQUIRED_NODES = (
    "MiniMaxH3ReferenceToVideo",
    "MiniMaxH3FunControlNetApply",
    "ModelPatchLoader",
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "LoadVideo",
    "GetVideoComponents",
    "SamplerCustomAdvanced",
    "SaveVideo",
    "H3ControlVideoGuard",
)


def control_header(path: Path) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(8)
        if len(raw) != 8:
            raise ValueError("Truncated safetensors file")
        length = struct.unpack("<Q", raw)[0]
        if length > 16 * 1024 * 1024:
            raise ValueError("Unexpected safetensors header size")
        header = json.loads(stream.read(length))
    blocks = sorted(
        {int(m.group(1)) for key in header if (m := re.search(r"control_blocks\.(\d+)\.", key))}
    )
    metadata = header.get("__metadata__", {})
    return {"blocks": blocks, "metadata": metadata}


def source_checks(comfy: Path, versions: dict) -> dict[str, bool]:
    stamp = comfy / ".h3-source.json"
    nodes = comfy / "comfy_extras/nodes_minimax_h3.py"
    loader = comfy / "comfy_extras/nodes_model_patch.py"
    text = nodes.read_text(encoding="utf-8") if nodes.is_file() else ""
    load_text = loader.read_text(encoding="utf-8") if loader.is_file() else ""
    return {
        "pinned_comfyui_source": stamp.is_file()
        and read_json(stamp).get("commit") == versions["comfyui_commit"],
        "reference_images_supported": "ref_images" in text and "MiniMaxH3ReferenceToVideo" in text,
        "control_video_supported": "MiniMaxH3FunControlNetApply" in text
        and '"control_video"' in text,
        "union2_post_norm_supported": "inpaint_masked_pixel_mode" in load_text
        and "post_norm" in load_text,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--require-cuda", action="store_true")
    parser.add_argument("--require-models", action="store_true")
    parser.add_argument(
        "--server", help="Optional live ComfyUI URL, normally http://127.0.0.1:6006"
    )
    parser.add_argument("--output", type=Path, default=ROOT / ".local/doctor.json")
    args = parser.parse_args()
    config = settings()
    versions = read_json(ROOT / "config/versions.json")
    comfy = Path(config.get("COMFYUI_DIR", ROOT / "runtime/ComfyUI"))
    checks = source_checks(comfy, versions)
    detail = {}
    if args.require_models:
        manifest = read_json(ROOT / "config/models.lock.json")
        for model in manifest["models"]:
            path = comfy / "models" / model["path"]
            checks["model_size:" + model["role"]] = (
                path.is_file() and path.stat().st_size == model["bytes"]
            )
            if model["role"] == "controlnet" and path.is_file():
                info = control_header(path)
                detail["controlnet_header"] = info
                checks["ten_control_blocks"] = info["blocks"] == list(range(10))
                checks["controlnet_post_norm_metadata"] = (
                    info["metadata"].get("inpaint_masked_pixel_mode") == "post_norm"
                )
    if args.require_cuda:
        import torch

        detail["torch"] = torch.__version__
        detail["torch_cuda"] = torch.version.cuda
        checks["torch_version"] = torch.__version__ == versions["torch"]
        checks["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            detail["gpu"] = torch.cuda.get_device_name(0)
            detail["vram_bytes"] = torch.cuda.get_device_properties(0).total_memory
    if args.server:
        base = args.server.rstrip("/")
        with urllib.request.urlopen(base + "/object_info", timeout=30) as response:
            info = json.load(response)
        for node in REQUIRED_NODES:
            checks["live_node:" + node] = node in info
        if "MiniMaxH3FunControlNetApply" in info:
            schema = info["MiniMaxH3FunControlNetApply"].get("input", {})
            names = {key for group in schema.values() if isinstance(group, dict) for key in group}
            checks["live_control_video_input"] = "control_video" in names
    result = {
        "checks": checks,
        "detail": detail,
        "passed": bool(checks) and all(checks.values()),
        "inference_tested": False,
        "visual_scale_consistency": "NOT_TESTED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
