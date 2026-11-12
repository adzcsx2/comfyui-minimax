"""Small, standard-library deployment helpers; never load user credentials."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def settings() -> dict[str, str]:
    values = {}
    for path in (ROOT / "config/mirrors.env", ROOT / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                raise ValueError(f"Invalid configuration line in {path.name}")
            values[key] = value.strip().strip('"').strip("'")
    values = {key: os.environ.get(key, value) for key, value in values.items()}
    for key in ("COMFYUI_DIR", "VENV_DIR", "MODEL_DIR", "PUBLIC_MODEL_ROOTS"):
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mirror_url(endpoint: str, suffix: str) -> str:
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("A mirror must be an HTTPS URL without credentials")
    if parsed.hostname in {"github.com", "raw.githubusercontent.com", "huggingface.co", "pypi.org"}:
        raise ValueError("An upstream origin was supplied where a mirror is required")
    return endpoint.rstrip("/") + "/" + suffix.lstrip("/")


def download(url: str, target: Path, expected_hash: str, expected_size: int | None = None) -> None:
    """Resume a transfer, validate bytes, then publish atomically; never overwrite a good file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if (expected_size is None or target.stat().st_size == expected_size) and sha256(
            target
        ) == expected_hash:
            return
        raise ValueError(f"Existing file failed integrity verification: {target.name}")
    partial = target.with_name(target.name + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    if expected_size is not None and offset > expected_size:
        raise ValueError(f"Partial download is larger than the expected file: {target.name}")
    if expected_size is None or offset != expected_size:
        headers = {"User-Agent": "comfyui-minimax/1", "Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=60
        ) as response:
            if offset and response.status == 206:
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith(f"bytes {offset}-"):
                    raise ValueError("The server returned an incorrect resume range")
                mode = "ab"
            elif response.status == 200:
                mode = "wb"
            else:
                raise ValueError(f"Unexpected download status: {response.status}")
            with partial.open(mode) as output:
                while block := response.read(8 * 1024 * 1024):
                    output.write(block)
                    if expected_size is not None and output.tell() > expected_size:
                        raise ValueError("Download exceeds its locked size")
    if expected_size is not None and partial.stat().st_size != expected_size:
        raise ValueError(f"Incomplete download: {target.name}")
    if sha256(partial) != expected_hash:
        raise ValueError(f"SHA-256 mismatch: {target.name}; partial file retained for diagnosis")
    partial.replace(target)


def extract_source(archive: Path, destination: Path, commit: str) -> None:
    """Extract only regular files/directories below the single locked archive root."""
    if destination.exists():
        stamp = destination / ".h3-source.json"
        if stamp.is_file() and read_json(stamp).get("commit") == commit:
            return
        raise ValueError(
            f"Refusing to replace an existing unrecognized ComfyUI directory: {destination}"
        )
    prefix = f"ComfyUI-{commit}/"
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        for member in members:
            if member.name.rstrip("/") == prefix.rstrip("/"):
                continue
            if not member.name.startswith(prefix) or not (member.isfile() or member.isdir()):
                raise ValueError("Unsafe or unexpected source archive member")
            relative = Path(member.name[len(prefix) :])
            if relative.is_absolute() or ".." in relative.parts or "\\" in member.name:
                raise ValueError("Unsafe source archive path")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".comfyui-unpack-", dir=destination.parent
        ) as temporary:
            staging = Path(temporary) / "ComfyUI"
            staging.mkdir()
            for member in members:
                relative = member.name[len(prefix) :] if member.name.startswith(prefix) else ""
                if not relative:
                    continue
                target = staging / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    stream = source.extractfile(member)
                    if stream is None:
                        raise ValueError("Could not read archive member")
                    with stream, target.open("wb") as output:
                        while block := stream.read(1024 * 1024):
                            output.write(block)
                    target.chmod(member.mode & 0o777)
            (staging / ".h3-source.json").write_text(
                json.dumps({"commit": commit}) + "\n", encoding="utf-8"
            )
            staging.rename(destination)
