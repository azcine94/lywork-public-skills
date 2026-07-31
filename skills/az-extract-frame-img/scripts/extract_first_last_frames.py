#!/usr/bin/env python3
"""Extract the first and final decoded video frames with FFmpeg."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
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
    streams = payload.get("streams") or []
    if not streams:
        fail("the input contains no readable video stream")

    raw_duration = (payload.get("format") or {}).get("duration")
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def overwrite_flag(overwrite: bool) -> str:
    return "-y" if overwrite else "-n"


def extract_first(
    ffmpeg: str, video: Path, output: Path, overwrite: bool
) -> None:
    run_checked(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            overwrite_flag(overwrite),
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


def extract_last(
    ffmpeg: str,
    video: Path,
    output: Path,
    duration: float | None,
    overwrite: bool,
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
        overwrite_flag(overwrite),
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
        # Some containers do not support seeking from EOF. Decode the full video
        # as a slower but accurate fallback, continually replacing one image.
        fallback = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            overwrite_flag(overwrite),
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
        description="Extract the first and final decoded frames from a video."
    )
    parser.add_argument("video", type=Path, help="Path to the source video")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Destination directory (default: <video-name>_frames beside the video)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing first_frame.png and last_frame.png",
    )
    parser.add_argument("--ffmpeg", help="Explicit path to the ffmpeg executable")
    parser.add_argument("--ffprobe", help="Explicit path to the ffprobe executable")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video = args.video.expanduser().resolve()
    if not video.is_file():
        fail(f"video file does not exist: {video}")

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else video.parent / f"{video.stem}_frames"
    )
    first = output_dir / "first_frame.png"
    last = output_dir / "last_frame.png"

    if not args.overwrite:
        collisions = [str(path) for path in (first, last) if path.exists()]
        if collisions:
            fail(
                "output already exists; choose another --output-dir or use "
                f"--overwrite: {', '.join(collisions)}"
            )

    ffmpeg = resolve_executable(args.ffmpeg, "ffmpeg")
    ffprobe = resolve_executable(args.ffprobe, "ffprobe")
    output_dir.mkdir(parents=True, exist_ok=True)

    first_tmp = output_dir / ".first_frame.tmp.png"
    last_tmp = output_dir / ".last_frame.tmp.png"
    for temporary in (first_tmp, last_tmp):
        temporary.unlink(missing_ok=True)

    try:
        duration = probe_duration(ffprobe, video)
        extract_first(ffmpeg, video, first_tmp, overwrite=True)
        extract_last(ffmpeg, video, last_tmp, duration, overwrite=True)

        for frame in (first_tmp, last_tmp):
            if not frame.is_file() or frame.stat().st_size == 0:
                raise RuntimeError(f"FFmpeg did not create a valid frame: {frame}")

        first_tmp.replace(first)
        last_tmp.replace(last)
    except (RuntimeError, json.JSONDecodeError) as exc:
        for temporary in (first_tmp, last_tmp):
            temporary.unlink(missing_ok=True)
        fail(str(exc))

    payload = {
        "video": str(video),
        "duration_seconds": duration,
        "first_frame": str(first.resolve()),
        "last_frame": str(last.resolve()),
        "same_frame": sha256(first) == sha256(last),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
