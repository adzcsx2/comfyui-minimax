"""Fetch an immutable, hash-checked ComfyUI archive through the configured mirror."""

import argparse
from pathlib import Path

from common import ROOT, download, extract_source, mirror_url, read_json, settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    config = settings()
    versions = read_json(ROOT / "config/versions.json")
    commit = versions["comfyui_commit"]
    destination = args.destination or Path(config.get("COMFYUI_DIR", ROOT / "runtime/ComfyUI"))
    archive = ROOT / "runtime/cache" / f"comfyui-{commit}.tar.gz"
    suffix = f"https://github.com/{versions['comfyui_repository']}/archive/{commit}.tar.gz"
    download(
        mirror_url(config["GITHUB_MIRROR"], suffix), archive, versions["comfyui_archive_sha256"]
    )
    extract_source(archive, destination, commit)
    print(f"ComfyUI source verified: {commit}")


if __name__ == "__main__":
    main()
