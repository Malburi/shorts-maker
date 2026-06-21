import asyncio
import subprocess
from pathlib import Path
from openai import OpenAI


def _client() -> OpenAI:
    return OpenAI()


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


async def extract_frame(video_path: Path, clip_offset: float, output_path: Path) -> Path:
    """Extract frame at clip_offset seconds from the start of the clip."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(max(0.0, clip_offset)),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(output_path),
    ]
    await asyncio.to_thread(_run, cmd)

    if not output_path.exists() or output_path.stat().st_size < 100:
        cmd[3] = "0"
        await asyncio.to_thread(_run, cmd)

    return output_path


def _generate_ai_sync(prompt: str, output_path: Path) -> bool:
    client = _client()
    try:
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1536",  # portrait (gpt-image-1 지원 최대 세로)
            quality="low",
            n=1,
        )
        image_bytes = resp.data[0].b64_json
        if image_bytes:
            import base64
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(image_bytes))
            return True
        # url 방식 fallback
        url = resp.data[0].url
        if url:
            import urllib.request
            urllib.request.urlretrieve(url, output_path)
            return True
        return False
    except Exception:
        return False


async def generate_ai_thumbnail(clip_path: Path, title: str, reason: str, output_path: Path) -> bool:
    prompt = (
        f"YouTube Shorts thumbnail for a video titled '{title}'. "
        f"Content: {reason}. "
        "Eye-catching design, bold colors, dramatic lighting, "
        "9:16 vertical portrait format, Korean YouTube style, no text."
    )
    return await asyncio.to_thread(_generate_ai_sync, prompt, output_path)


async def make_thumbnail(
    clip_path: Path,
    clip_duration: float,
    title: str,
    reason: str,
    output_path: Path,
    use_ai: bool = True,
) -> Path:
    if use_ai:
        success = await generate_ai_thumbnail(clip_path, title, reason, output_path)
        if success:
            return output_path

    # Fallback: extract frame at 1/3 into the clip
    offset = clip_duration / 3
    return await extract_frame(clip_path, offset, output_path)
