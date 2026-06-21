import asyncio
import subprocess
from pathlib import Path
from ..models import KeyMoment
from . import smart_crop


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


async def make_short(video_path: Path, moment: KeyMoment, output_path: Path) -> Path:
    """Clip and reformat to 9:16 vertical (1080x1920) with fade in/out.

    인물(얼굴)을 감지해 그 위치 중심으로 크롭한다. 감지에 실패하면
    잘라내지 않고 풀샷 + 위아래 검은 여백(레터박스)으로 폴백한다.
    """
    duration = moment.end - moment.start
    fade = (
        f"fade=t=in:st=0:d=0.5,"
        f"fade=t=out:st={max(0, duration - 0.5):.2f}:d=0.5"
    )

    crop = await asyncio.to_thread(
        smart_crop.compute_crop_params, video_path, moment.start, moment.end
    )

    if crop:
        # 인물 중심 크롭 → 9:16로 스케일
        geometry = (
            f"crop=w={crop['w']}:h={crop['h']}:x={crop['x']}:y={crop['y']},"
            "scale=1080:1920,"
        )
    else:
        # 레터박스 폴백: 풀샷을 가로폭에 맞춰 넣고 위아래 검은 여백 (잘림 없음)
        geometry = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        )

    vf = geometry + fade

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
