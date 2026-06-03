import asyncio
import subprocess
from pathlib import Path
from openai import OpenAI


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


def _client() -> OpenAI:
    return OpenAI()


async def extract_audio(video_path: Path, output_path: Path) -> Path:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
        str(output_path),
    ]
    result = await asyncio.to_thread(_run, cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr.decode()[-300:]}")
    return output_path


def _transcribe_sync(audio_path: Path) -> dict:
    client = _client()
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="ko",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    segments = [
        {"start": seg.start, "end": seg.end, "text": seg.text}
        for seg in response.segments
    ]
    return {"text": response.text, "segments": segments}


async def transcribe(audio_path: Path) -> dict:
    return await asyncio.to_thread(_transcribe_sync, audio_path)
