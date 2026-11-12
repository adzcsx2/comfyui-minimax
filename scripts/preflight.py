"""Check control media and API bindings without starting generation."""

from __future__ import annotations

import argparse
import json
import subprocess
from fractions import Fraction
from pathlib import Path

from common import ROOT, read_json


def validate_graph(graph: dict) -> list[str]:
    problems = []
    control = graph["8"]["inputs"]
    ref = graph["13"]["inputs"]
    if control.get("control_video") != ["22", 0] or control.get("model_patch") != ["5", 0]:
        problems.append("The control branch is not bound to the video guard / model patch")
    for node in ("15", "17"):
        if graph[node]["inputs"].get("model") != ["8", 0]:
            problems.append("Sampling must use the patched model")
    if "2.0" not in graph["5"]["inputs"].get("name", ""):
        problems.append("The model patch must be Union 2.0")
    for i in range(4):
        if ref.get(f"ref_images.ref_image_{i}") != [str(9 + i), 0]:
            problems.append(f"Reference image {i + 1} is not bound in order")
    expected = graph["22"]["inputs"]
    if (ref["width"], ref["height"], ref["length"]) != (
        expected["width"],
        expected["height"],
        expected["expected_frames"],
    ):
        problems.append("Reference conditioning and control-video geometry disagree")
    return problems


def inspect_video(path: Path, width: int, height: int, frames: int) -> dict:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-count_frames",
        "-show_entries",
        "stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames",
        "-of",
        "json",
        str(path),
    ]
    data = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
    stream = data["streams"][0]
    actual_frames = int(stream["nb_read_frames"])
    fps = float(Fraction(stream["avg_frame_rate"]))
    if (stream["width"], stream["height"], actual_frames) != (width, height, frames) or abs(
        fps - 24
    ) > 0.01:
        raise ValueError(
            "Control clip must match the graph: exact dimensions / frame count and 24 fps"
        )
    return {
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
        "duration": frames / fps,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workflow", type=Path, default=ROOT / "workflows/h3-depth-ref2va-api.json"
    )
    parser.add_argument("--control", type=Path)
    args = parser.parse_args()
    graph = read_json(args.workflow)
    problems = validate_graph(graph)
    if problems:
        raise SystemExit("\n".join(problems))
    if args.control:
        ref = graph["13"]["inputs"]
        print(
            json.dumps(
                inspect_video(args.control, ref["width"], ref["height"], ref["length"]), indent=2
            )
        )
    print("Graph bindings verified. No generation task was submitted.")


if __name__ == "__main__":
    main()
