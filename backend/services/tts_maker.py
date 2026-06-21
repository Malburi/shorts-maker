"""
한국어 TTS 생성 + ffprobe로 오디오 길이 측정.
edge-tts (Microsoft Azure Neural TTS) ko-KR-SunHiNeural 기본 사용.
실패 시 OpenAI TTS onyx로 폴백.
"""
import asyncio
import subprocess
from pathlib import Path

import edge_tts
from openai import OpenAI

KO_VOICE = "ko-KR-SunHiNeural"   # Microsoft Azure Neural 한국어 (여성, 자연스러운 억양)
KO_VOICE_MALE = "ko-KR-InJoonNeural"  # 남성 대안


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


async def _tts_edge(text: str, output_path: Path) -> None:
    """edge-tts로 한국어 음성 생성."""
    communicate = edge_tts.Communicate(text, voice=KO_VOICE, rate="+0%", volume="+0%")
    await communicate.save(str(output_path))


def _tts_openai_fallback(text: str, output_path: Path) -> None:
    """OpenAI TTS 폴백 (edge-tts 실패 시)."""
    client = OpenAI()
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice="onyx",   # onyx가 한국어 발음 가장 자연스러움
        input=text,
        response_format="mp3",
    )
    response.stream_to_file(str(output_path))


async def get_audio_duration(audio_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(audio_path),
    ]
    result = await asyncio.to_thread(_run, cmd)
    try:
        return float(result.stdout.decode().strip())
    except (ValueError, AttributeError):
        return 5.0


async def generate_tts(text: str, output_path: Path) -> float:
    """TTS 생성 후 오디오 길이(초) 반환. edge-tts 실패 시 OpenAI로 폴백."""
    try:
        await _tts_edge(text, output_path)
    except Exception:
        await asyncio.to_thread(_tts_openai_fallback, text, output_path)
    return await get_audio_duration(output_path)
