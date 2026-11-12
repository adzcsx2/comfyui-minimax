"""Optional bounded-range transfer for a pinned model when a long response stalls."""
from __future__ import annotations

import argparse
import concurrent.futures
import time
import urllib.parse
import urllib.request
from pathlib import Path

from common import ROOT, mirror_url, read_json, settings, sha256


def download_ranges(url, target, expected_hash, total, connections=8, chunk_size=32 * 1024**2):
    if not 1 <= connections <= 16 or chunk_size < 1 or total < 1:
        raise ValueError("Invalid range-transfer limits")
    if target.exists():
        if target.stat().st_size == total and sha256(target) == expected_hash:
            return
        raise ValueError("Existing model differs from the lock; refusing to overwrite it")
    folder = target.with_name(target.name + ".chunks")
    folder.mkdir(parents=True, exist_ok=True)
    count = (total + chunk_size - 1) // chunk_size

    def fetch(index):
        start = index * chunk_size
        end = min(total, start + chunk_size) - 1
        path = folder / f"{index:06}.part"
        if path.exists() and path.stat().st_size == end - start + 1:
            return path
        temporary = path.with_suffix(".tmp")
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    url,
                    headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
                )
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != (
                        f"bytes {start}-{end}/{total}"
                    ):
                        raise ValueError("Mirror did not honor the exact byte range")
                    with temporary.open("wb") as output:
                        while block := response.read(1024 * 1024):
                            output.write(block)
                            if output.tell() > end - start + 1:
                                raise ValueError("Range response exceeded its locked length")
                if temporary.stat().st_size != end - start + 1:
                    raise ValueError("Incomplete range response")
                temporary.replace(path)
                print(f"Model chunk {index + 1}/{count} received", flush=True)
                return path
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=connections) as pool:
        futures = [pool.submit(fetch, index) for index in range(count)]
        try:
            paths = [future.result() for future in futures]
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    assembled = target.with_name(target.name + ".assembled.part")
    with assembled.open("wb") as output:
        for path in paths:
            with path.open("rb") as source:
                while block := source.read(8 * 1024 * 1024):
                    output.write(block)
    if assembled.stat().st_size != total or sha256(assembled) != expected_hash:
        raise ValueError("Assembled model failed integrity verification; chunks retained")
    assembled.replace(target)
    for path in paths:
        path.unlink()
    try:
        folder.rmdir()
    except OSError:
        pass  # Never remove unexpected files from the staging folder.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", default="controlnet")
    parser.add_argument("--connections", type=int, default=8)
    args = parser.parse_args()
    config = settings()
    lock = read_json(ROOT / "config/models.lock.json")
    matches = [item for item in lock["models"] if item["role"] == args.role]
    if len(matches) != 1:
        raise SystemExit("Select one role from config/models.lock.json")
    item = matches[0]
    cache = Path(config.get("MODEL_DIR", ROOT / "runtime/model-cache"))
    target = cache / item["path"]
    suffix = f"{lock['repository']}/resolve/{lock['revision']}/{urllib.parse.quote(item['path'])}"
    download_ranges(
        mirror_url(config["HF_ENDPOINT"], suffix), target,
        item["sha256"], item["bytes"], args.connections,
    )
    print(f"Pinned model verified: {item['role']}. Run download_models.py --link-only next.")


if __name__ == "__main__":
    main()
