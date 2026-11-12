"""Verify/reuse public models, or download exact locked files through HF_ENDPOINT."""

from __future__ import annotations

import argparse
import os
import shutil
import urllib.parse
from pathlib import Path

from common import ROOT, download, mirror_url, read_json, settings, sha256


def verified(path: Path, item: dict) -> bool:
    return (
        path.is_file() and path.stat().st_size == item["bytes"] and sha256(path) == item["sha256"]
    )


def public_candidates(roots: str, wanted: set[str]) -> dict[str, list[Path]]:
    result = {}
    seen = set()
    for name in filter(None, roots.split(os.pathsep)):
        root = Path(name)
        if not root.is_dir():
            continue
        for directory, _, files in os.walk(root, followlinks=False):
            for filename in wanted.intersection(files):
                candidate = Path(directory) / filename
                key = (filename, candidate.resolve())
                if key not in seen:
                    result.setdefault(filename, []).append(candidate)
                    seen.add(key)
    return result


def select_public(item: dict, candidates: dict[str, list[Path]]) -> Path | None:
    names = [Path(item["path"]).name, *item.get("public_aliases", [])]
    for name in names:
        for candidate in candidates.get(name, []):
            if verified(candidate, item):
                return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument(
        "--link-only", action="store_true", help="Link verified local/public models; never download"
    )
    parser.add_argument("--no-public", action="store_true")
    args = parser.parse_args()
    config = settings()
    manifest = read_json(ROOT / "config/models.lock.json")
    comfy = Path(config.get("COMFYUI_DIR", ROOT / "runtime/ComfyUI"))
    cache = Path(config.get("MODEL_DIR", ROOT / "runtime/models"))
    candidates = (
        {}
        if args.no_public
        else public_candidates(
            config.get("PUBLIC_MODEL_ROOTS", ""),
            {
                name
                for item in manifest["models"]
                for name in [Path(item["path"]).name, *item.get("public_aliases", [])]
            },
        )
    )
    failures = []
    for item in manifest["models"]:
        name = Path(item["path"]).name
        target = comfy / "models" / item["path"]
        if target.exists() and verified(target, item):
            print(f"VERIFIED {name}")
            continue
        if target.exists() or target.is_symlink():
            failures.append(f"Wrong or broken existing model: {name}")
            continue
        shared = select_public(item, candidates)
        if shared:
            if args.check_only:
                failures.append(
                    f"Verified public model is not linked yet: {name}; run without --check-only"
                )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(shared.resolve())
            print(f"PUBLIC_MODEL_VERIFIED {name}")
            continue
        stored = cache / item["path"]
        if args.check_only:
            failures.append(f"Missing model: {name}")
            continue
        if args.link_only and not stored.exists():
            failures.append(f"Missing model: {name}; run installation with --download-models once")
            continue
        stored.parent.mkdir(parents=True, exist_ok=True)
        if not stored.exists():
            partial = stored.with_name(stored.name + ".part")
            remaining = max(0, item["bytes"] - (partial.stat().st_size if partial.exists() else 0))
            if shutil.disk_usage(stored.parent).free < remaining + 1024**3:
                raise SystemExit(
                    f"Insufficient model storage for {name}; use a data disk or public model mount"
                )
        suffix = (
            f"{manifest['repository']}/resolve/{manifest['revision']}/"
            f"{urllib.parse.quote(item['path'])}"
        )
        print(f"DOWNLOADING {name}", flush=True)
        download(mirror_url(config["HF_ENDPOINT"], suffix), stored, item["sha256"], item["bytes"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(stored.resolve())
        print(f"VERIFIED {name}", flush=True)
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
