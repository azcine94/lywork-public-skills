#!/usr/bin/env python3
"""Probe a source video and extract representative frames for Seedance prompting."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import NoReturn


def fail(message: str) -> NoReturn:
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


def parse_positive_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def parse_frame_rate(value: object) -> float | None:
    if not isinstance(value, str) or value in {"", "0/0", "N/A"}:
        return None
    try:
        parsed = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def probe_video(ffprobe: str, video: Path) -> dict[str, object]:
    result = run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            (
                "stream=index,codec_type,width,height,avg_frame_rate,"
                "r_frame_rate,duration:format=duration,format_name"
            ),
            "-of",
            "json",
            str(video),
        ],
        "video probe",
    )
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        fail("the input contains no readable video stream")

    duration = parse_positive_float((payload.get("format") or {}).get("duration"))
    if duration is None:
        duration = parse_positive_float(video_stream.get("duration"))
    if duration is None:
        fail("could not determine the source video duration")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width <= 0 or height <= 0:
        fail("could not determine the source video dimensions")

    fps = parse_frame_rate(video_stream.get("avg_frame_rate"))
    if fps is None:
        fps = parse_frame_rate(video_stream.get("r_frame_rate"))
    if fps is None:
        fail("could not determine the source video frame rate")

    divisor = math.gcd(width, height)
    return {
        "duration_seconds": duration,
        "fps": fps,
        "width": width,
        "height": height,
        "aspect_ratio": f"{width // divisor}:{height // divisor}",
        "has_audio": any(
            stream.get("codec_type") == "audio" for stream in streams
        ),
        "format_name": (payload.get("format") or {}).get("format_name"),
    }


def extract_frame(
    ffmpeg: str,
    video: Path,
    timestamp: float,
    output: Path,
) -> None:
    temporary = output.with_name(f".{output.stem}.tmp{output.suffix}")
    temporary.unlink(missing_ok=True)
    try:
        run_checked(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-ss",
                f"{timestamp:.6f}",
                "-i",
                str(video),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                str(temporary),
            ],
            f"representative-frame extraction at {timestamp:.3f}s",
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError(f"FFmpeg did not create a valid frame: {temporary}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a source video and extract frames at 25%, 50%, and 75% "
            "for Seedance prompt analysis."
        )
    )
    parser.add_argument("video", type=Path, help="Path to the original source video")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Destination directory (default: <video-name>_seedance_analysis)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing representative frame files",
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
        else video.parent / f"{video.stem}_seedance_analysis"
    )
    frames = {
        "25_percent": output_dir / "sample_25.png",
        "50_percent": output_dir / "sample_50.png",
        "75_percent": output_dir / "sample_75.png",
    }
    if not args.overwrite:
        collisions = [str(path) for path in frames.values() if path.exists()]
        if collisions:
            fail(
                "output already exists; choose another --output-dir or use "
                f"--overwrite: {', '.join(collisions)}"
            )

    ffmpeg = resolve_executable(args.ffmpeg, "ffmpeg")
    ffprobe = resolve_executable(args.ffprobe, "ffprobe")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        metadata = probe_video(ffprobe, video)
        duration = float(metadata["duration_seconds"])
        timestamps = {
            "25_percent": duration * 0.25,
            "50_percent": duration * 0.50,
            "75_percent": duration * 0.75,
        }
        for key, output in frames.items():
            extract_frame(ffmpeg, video, timestamps[key], output)
    except (RuntimeError, json.JSONDecodeError) as exc:
        fail(str(exc))

    payload = {
        "video": str(video),
        **metadata,
        "within_seedance_15s_limit": float(metadata["duration_seconds"]) <= 15.0,
        "representative_frames": {
            key: {
                "timestamp_seconds": timestamps[key],
                "path": str(path.resolve()),
            }
            for key, path in frames.items()
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
