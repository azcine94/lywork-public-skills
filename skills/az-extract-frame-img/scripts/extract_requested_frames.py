#!/usr/bin/env python3
"""Extract only the decoded video frames explicitly requested by the user."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def fail(message: str) -> "NoReturn":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def resolve_executable(value: str | None, default_name: str) -> str:
    candidate = value or shutil.which(default_name)
    if not candidate:
        fail(
            f"{default_name} was not found. Install FFmpeg and ensure "
            f"{default_name} is available on PATH."
        )
    return str(Path(candidate).expanduser())


def run_checked(command: list[str], purpose: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"{purpose} failed: {details[-4000:]}")
    return result


def probe_duration(ffprobe: str, video: Path) -> float | None:
    result = run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=index:format=duration",
            "-of",
            "json",
            str(video),
        ],
        "video probe",
    )
    payload = json.loads(result.stdout)
    if not (payload.get("streams") or []):
        fail("the input contains no readable video stream")

    raw_duration = (payload.get("format") or {}).get("duration")
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


@dataclass(frozen=True)
class FrameRequest:
    selector: str
    kind: str
    ordinal: int | None

    @property
    def semantic_key(self) -> str:
        if self.kind == "first":
            return "ordinal:1"
        if self.kind == "number":
            return f"ordinal:{self.ordinal}"
        return "last"

    @property
    def filename(self) -> str:
        if self.kind == "first":
            return "first_frame.png"
        if self.kind == "last":
            return "last_frame.png"
        return f"frame_{self.ordinal:06d}.png"


def parse_selector(value: str) -> FrameRequest:
    normalized = value.strip().lower()
    if normalized in {"first", "首帧"}:
        return FrameRequest(selector=value, kind="first", ordinal=1)
    if normalized in {"last", "尾帧"}:
        return FrameRequest(selector=value, kind="last", ordinal=None)
    if re.fullmatch(r"[1-9]\d*", normalized):
        return FrameRequest(
            selector=value,
            kind="number",
            ordinal=int(normalized),
        )
    raise argparse.ArgumentTypeError(
        f"invalid frame selector {value!r}; use first, last, or a positive 1-based frame number"
    )


def unique_requests(values: list[FrameRequest]) -> list[FrameRequest]:
    requests: list[FrameRequest] = []
    seen: set[str] = set()
    for request in values:
        # "first" and frame 1 refer to the same decoded frame. Preserve whichever
        # spelling appeared first so repeated user intent never creates extra output.
        if request.semantic_key in seen:
            continue
        seen.add(request.semantic_key)
        requests.append(request)
    return requests


def extract_first(ffmpeg: str, video: Path, output: Path) -> None:
    run_checked(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            str(output),
        ],
        "first-frame extraction",
    )


def extract_numbered(
    ffmpeg: str,
    video: Path,
    output: Path,
    ordinal: int,
) -> None:
    # User-facing frame numbers are 1-based; FFmpeg's decoded-frame n is 0-based.
    expression = f"select=eq(n\\,{ordinal - 1})"
    run_checked(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-vf",
            expression,
            "-frames:v",
            "1",
            "-fps_mode",
            "vfr",
            str(output),
        ],
        f"frame {ordinal} extraction",
    )


def extract_last(
    ffmpeg: str,
    video: Path,
    output: Path,
    duration: float | None,
) -> None:
    input_seek = (
        ["-ss", f"{max(0.0, duration - 2.0):.6f}"]
        if duration is not None
        else ["-sseof", "-2"]
    )
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        *input_seek,
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-fps_mode",
        "vfr",
        "-update",
        "1",
        str(output),
    ]

    try:
        run_checked(command, "last-frame extraction")
    except RuntimeError:
        if duration is not None:
            raise
        # Some containers cannot seek from EOF. Decode the full stream as a slower
        # fallback and continually replace the same temporary image.
        fallback = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-fps_mode",
            "vfr",
            "-update",
            "1",
            str(output),
        ]
        run_checked(fallback, "last-frame extraction fallback")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract only explicitly requested decoded frames from a video."
    )
    parser.add_argument("video", type=Path, help="Path to the source video")
    parser.add_argument(
        "--frame",
        action="append",
        required=True,
        type=parse_selector,
        metavar="SELECTOR",
        help="Frame selector: first, last, or a positive 1-based frame number; repeat as needed",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Destination directory (default: <video-name>_frames beside the video)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing outputs for the requested selectors only",
    )
    parser.add_argument("--ffmpeg", help="Explicit path to the ffmpeg executable")
    parser.add_argument("--ffprobe", help="Explicit path to the ffprobe executable")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requests = unique_requests(args.frame)
    video = args.video.expanduser().resolve()
    if not video.is_file():
        fail(f"video file does not exist: {video}")

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else video.parent / f"{video.stem}_frames"
    )
    outputs = [(request, output_dir / request.filename) for request in requests]

    if not args.overwrite:
        collisions = [str(path) for _, path in outputs if path.exists()]
        if collisions:
            fail(
                "output already exists; choose another --output-dir or use "
                f"--overwrite: {', '.join(collisions)}"
            )

    ffmpeg = resolve_executable(args.ffmpeg, "ffmpeg")
    ffprobe = resolve_executable(args.ffprobe, "ffprobe")
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(ffprobe, video)
    temporary_outputs = [
        (request, output, output_dir / f".{output.stem}.tmp.png")
        for request, output in outputs
    ]
    for _, _, temporary in temporary_outputs:
        temporary.unlink(missing_ok=True)

    try:
        for request, _, temporary in temporary_outputs:
            if request.kind == "first":
                extract_first(ffmpeg, video, temporary)
            elif request.kind == "last":
                extract_last(ffmpeg, video, temporary, duration)
            else:
                extract_numbered(ffmpeg, video, temporary, request.ordinal or 0)

            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError(
                    f"requested {request.selector!r} is outside the decoded video or produced no frame"
                )

        for _, output, temporary in temporary_outputs:
            if args.overwrite:
                output.unlink(missing_ok=True)
            temporary.replace(output)
    except (RuntimeError, json.JSONDecodeError) as exc:
        for _, _, temporary in temporary_outputs:
            temporary.unlink(missing_ok=True)
        fail(str(exc))

    frame_payload = []
    hashes: dict[str, list[str]] = {}
    for request, output in outputs:
        resolved = output.resolve()
        frame_payload.append(
            {
                "selector": request.selector,
                "kind": request.kind,
                "ordinal": request.ordinal,
                "output": str(resolved),
            }
        )
        hashes.setdefault(sha256(resolved), []).append(request.selector)

    payload = {
        "video": str(video),
        "duration_seconds": duration,
        "frames": frame_payload,
        "duplicate_content_groups": [
            selectors for selectors in hashes.values() if len(selectors) > 1
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
