import asyncio
import json
import re
import os
import time
from google import genai
from google.genai import types
from ..models import KeyMoment


def _client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]

SYSTEM_PROMPT = """당신은 SNS 숏폼 콘텐츠 전문가입니다.
주어진 영상 전사 텍스트(타임스탬프 포함)에서 쇼츠로 만들기 좋은 핵심 장면 3~5개를 선정하세요.

선정 기준:
- 드라마틱한 순간, 핵심 인사이트, 유머, 감동적인 장면
- 각 클립은 30~90초 사이
- 클립끼리 겹치지 않게

반드시 아래 JSON 형식으로만 응답하세요 (마크다운 없이):
{"moments": [{"index": 0, "title": "클립 제목", "start": 10.5, "end": 55.0, "reason": "선정 이유"}]}"""


def _select_sync(transcript_text: str, total_duration: float) -> list:
    client = _client()
    prompt = f"{SYSTEM_PROMPT}\n\n영상 총 길이: {total_duration:.0f}초\n\n전사 내용:\n{transcript_text}"

    last_err = None
    for model in MODELS:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.7,
                    ),
                )
                text = response.text.strip()
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
                return json.loads(text).get("moments", [])

            except Exception as e:
                last_err = e
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    time.sleep(10 * (attempt + 1))
                    continue
                break

    raise last_err


async def select_key_moments(segments: list, total_duration: float) -> list[KeyMoment]:
    lines = []
    for seg in segments:
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"[{start:.1f}s ~ {end:.1f}s] {text}")
    transcript_text = "\n".join(lines)

    moments_raw = await asyncio.to_thread(_select_sync, transcript_text, total_duration)

    moments = []
    for m in moments_raw:
        start = max(0.0, float(m["start"]))
        end = min(total_duration, float(m["end"]))
        if end - start < 10:
            continue
        moments.append(KeyMoment(
            index=m["index"],
            title=m["title"],
            start=start,
            end=end,
            reason=m["reason"],
        ))
    return moments[:5]
