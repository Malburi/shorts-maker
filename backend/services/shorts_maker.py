import asyncio
import subprocess
from pathlib import Path
from ..models import KeyMoment


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


async def make_short(video_path: Path, moment: KeyMoment, output_path: Path) -> Path:
    """Clip and reformat to 9:16 vertical (1080x1920) with fade in/out."""
    duration = moment.end - moment.start

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"fade=t=in:st=0:d=0.5,"
        f"fade=t=out:st={max(0, duration - 0.5):.2f}:d=0.5"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(moment.start),
        "-i", str(video_path),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = await asyncio.to_thread(_run, cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg shorts failed [{moment.index}]: {result.stderr.decode()[-500:]}")
    return output_path


async def concat_shorts(clip_paths: list[Path], output_path: Path) -> Path:
    """Concatenate multiple clips into a single highlight reel using ffmpeg concat demuxer."""
    list_path = output_path.parent / "concat_list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(output_path),
    ]

    result = await asyncio.to_thread(_run, cmd)
    list_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed: {result.stderr.decode()[-500:]}")
    return output_path


async def get_video_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(video_path),
    ]
    result = await asyncio.to_thread(_run, cmd)
    try:
        return float(result.stdout.decode().strip())
    except (ValueError, AttributeError):
        return 0.0
