"""
Nano Banana(Gemini 2.5 Flash Image) 이미지 생성 + Veo 3.1 Fast 영상 생성.

창작 파이프라인의 장면 비주얼을 담당한다:
  image_prompt → Nano Banana(9:16 이미지) → Veo(이미지→영상, 9:16 클립)

Veo는 long-running operation이라 폴링이 필요하고 비용이 크다. 실패/타임아웃은
예외로 올려 호출부(create_pipeline)가 정지이미지 Ken Burns 폴백을 쓰도록 한다.
"""
import asyncio
import os
import time
from pathlib import Path

from google import genai
from google.genai import types

# ── 모델 / 설정 ────────────────────────────────────────────────────────
IMAGE_MODEL = "gemini-2.5-flash-image"          # Nano Banana
VIDEO_MODEL = "veo-3.1-fast-generate-preview"   # Veo 3.1 Fast

VEO_RESOLUTION = "720p"        # 9:16 720p (=720x1280); ffmpeg에서 1080x1920으로 스케일
VEO_POLL_INTERVAL = 10         # 초
VEO_MAX_WAIT = 360             # 초 (타임아웃 → 폴백)
IMAGE_RETRIES = 3


def _client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


# ── Nano Banana 이미지 ─────────────────────────────────────────────────
def _gen_image_sync(prompt: str, reference: tuple[bytes, str] | None = None) -> tuple[bytes, str]:
    """9:16 이미지 바이트와 mime 타입을 반환. 실패 시 마지막 예외를 올림.

    reference가 주어지면(=(bytes, mime)) 그 이미지를 함께 입력해 화풍·인물·배경을
    일관되게 유지한다(기준 이미지 고정).
    """
    client = _client()
    last_err = None
    for attempt in range(IMAGE_RETRIES):
        try:
            if reference is not None:
                ref_bytes, ref_mime = reference
                contents = [
                    types.Part.from_bytes(data=ref_bytes, mime_type=ref_mime),
                    prompt,
                ]
            else:
                contents = [prompt]

            resp = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio="9:16"),
                ),
            )
            parts = resp.candidates[0].content.parts
            for part in parts:
                if getattr(part, "inline_data", None) is not None:
                    return part.inline_data.data, (part.inline_data.mime_type or "image/png")
            raise RuntimeError("Nano Banana 응답에 이미지가 없습니다.")
        except Exception as e:
            last_err = e
            if any(x in str(e) for x in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")):
                time.sleep(8 * (attempt + 1))
                continue
            if attempt < IMAGE_RETRIES - 1:
                time.sleep(3)
                continue
            break
    raise last_err


async def generate_image(prompt: str, output_path: Path,
                         reference_path: Path | None = None) -> Path:
    """Nano Banana 이미지를 생성해 output_path에 저장.
    reference_path가 주어지면 그 이미지를 기준으로 일관성을 유지한다."""
    reference = None
    if reference_path is not None and reference_path.exists():
        suffix = reference_path.suffix.lower()
        mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
        reference = (reference_path.read_bytes(), mime)

    img_bytes, _ = await asyncio.to_thread(_gen_image_sync, prompt, reference)
    with open(output_path, "wb") as f:
        f.write(img_bytes)
    return output_path


# ── Veo 영상 ───────────────────────────────────────────────────────────
def _gen_video_sync(image_path: Path, prompt: str, duration: int, output_path: Path) -> None:
    """
    이미지→영상(Veo). 성공 시 output_path에 mp4 저장.
    실패/타임아웃은 예외를 올려 호출부가 폴백하도록 한다.
    """
    client = _client()
    img_bytes = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"

    operation = client.models.generate_videos(
        model=VIDEO_MODEL,
        prompt=prompt,
        image=types.Image(image_bytes=img_bytes, mime_type=mime),
        config=types.GenerateVideosConfig(
            aspect_ratio="9:16",
            resolution=VEO_RESOLUTION,
            duration_seconds=duration,
            number_of_videos=1,
        ),
        # 참고: generate_audio는 Vertex(Enterprise) 전용. Developer API 키에선 미지원이라
        # 지정하지 않는다. Veo가 생성한 오디오는 ffmpeg 합성 시 -map 0:v로 버리고 TTS를 쓴다.
    )

    waited = 0
    while not operation.done:
        if waited >= VEO_MAX_WAIT:
            raise TimeoutError(f"Veo 생성 타임아웃 ({VEO_MAX_WAIT}s)")
        time.sleep(VEO_POLL_INTERVAL)
        waited += VEO_POLL_INTERVAL
        operation = client.operations.get(operation)

    if getattr(operation, "error", None):
        raise RuntimeError(f"Veo 오류: {operation.error}")

    videos = operation.response.generated_videos
    if not videos:
        raise RuntimeError("Veo 응답에 영상이 없습니다.")

    gv = videos[0]
    client.files.download(file=gv.video)
    gv.video.save(str(output_path))


async def generate_video(image_path: Path, prompt: str, duration: int, output_path: Path) -> None:
    """Veo 이미지→영상 생성. 실패 시 예외 전파(호출부가 폴백)."""
    await asyncio.to_thread(_gen_video_sync, image_path, prompt, duration, output_path)


def pick_duration(tts_duration: float) -> int:
    """나레이션 길이에 맞춰 Veo 지원 길이(4/6/8초) 선택 — 짧은 장면은 비용 절약."""
    if tts_duration <= 4:
        return 4
    if tts_duration <= 6:
        return 6
    return 8
