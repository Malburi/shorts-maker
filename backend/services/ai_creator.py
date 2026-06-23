"""
단일 프롬프트 → 웹 검색 → 일관성 있는 숏폼 스크립트 생성.

사용자가 한 칸에 자유롭게 적은 프롬프트(주제·스타일·길이 등)를 받아
실시간 웹 검색으로 사실 데이터를 보강하고, GPT-4o로 전체 영상의 통일된
비주얼 기준(visual_style) + 장면별 나레이션/이미지 프롬프트를 한 번에 생성한다.
"""
import asyncio
import json
from openai import OpenAI
from .searcher import web_search, format_search_context

_SCRIPT_SYSTEM = """\
당신은 유튜브 숏폼 전문 작가 겸 아트 디렉터입니다.
사용자가 자유롭게 적은 하나의 프롬프트(주제·원하는 분위기·길이 등이 섞여 있을 수 있음)를 받아,
일관성 있는 한 편의 숏폼 영상 대본을 만듭니다. 반드시 아래 JSON 형식으로만 응답하세요.

{
  "title": "영상 제목 (20자 이내)",
  "target_duration": 60,
  "visual_style": "English master visual style for the WHOLE video. One consistent art style, color palette, lighting, and a recurring main subject/character + setting that appears across every scene. This is used to generate one anchor image that all scenes stay consistent with. Be concrete and detailed (60+ words). No text overlay.",
  "scenes": [
    {
      "order": 1,
      "narration": "한국어 나레이션 (TTS용, 3-6문장. 충분히 길고 구체적으로.)",
      "image_prompt": "English: THIS scene's specific moment/action/composition ONLY. Assume the same character, art style, palette, and setting as visual_style (do NOT re-describe the whole style). Cinematic, 9:16 vertical, no text overlay."
    }
  ]
}

규칙:
- visual_style은 전체 영상을 관통하는 '하나의 룩'입니다. 등장 인물/피사체·배경·화풍·색감·조명을 구체적으로 고정하세요.
- 각 장면 image_prompt는 visual_style을 반복 설명하지 말고, 그 장면 고유의 동작·구도·순간만 묘사하세요 (일관성은 기준 이미지로 유지됨).
- 영상은 하드 컷이 아니라 '한 컷처럼 이어지는 연속 샷'입니다. 2번 장면부터 image_prompt는 직전 장면에서 카메라·피사체가 자연스럽게 이어져 발전하는 동작/구도로 묘사하세요(장소·구도가 갑자기 튀지 않게).
- 프롬프트에 길이 언급이 있으면 target_duration에 반영(30/60/90), 없으면 30.
- 각 장면은 약 6초입니다. 장면 수 = target_duration ÷ 6 (30초→5개, 60초→10개, 90초→15개). 이 개수를 반드시 지키세요.
- 나레이션은 장면당 **딱 1문장**(한국어로 6초 내외 분량, 약 25~40자). 길게 쓰지 마세요. 여러 장면의 문장이 이어지며 하나의 이야기를 이루게 하세요. 숫자·사례로 신뢰도를 높이되 한 문장에 한 가지만 담으세요.
- 웹 검색 결과가 제공되면 최신 사실·수치를 나레이션에 자연스럽게 반영하세요.
- narration은 한국어, visual_style과 image_prompt는 영어.
- JSON 외 다른 텍스트는 절대 출력 금지
"""


def _generate_script_sync(prompt: str, search_context: str = "") -> dict:
    client = OpenAI()
    parts = [f"사용자 프롬프트:\n{prompt}"]
    if search_context:
        parts.append("")
        parts.append(search_context)
    user_prompt = "\n".join(parts)

    resp = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": _SCRIPT_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        # gpt-5.5는 기본 temperature(1)만 지원 — 커스텀 temperature 지정 시 400 에러
    )
    return json.loads(resp.choices[0].message.content)


async def generate_script(prompt: str) -> dict:
    """단일 프롬프트로 웹 검색 + 일관성 있는 장면별 스크립트를 생성한다.

    Returns:
        {"script": dict, "search_count": int, "search_snippets": list[str]}
    """
    search_results = await web_search(prompt, max_results=6)
    search_context = format_search_context(search_results)

    script = await asyncio.to_thread(_generate_script_sync, prompt, search_context)

    snippets = [
        r.get("title", "").strip()
        for r in search_results
        if r.get("title", "").strip()
    ][:5]

    return {
        "script": script,
        "search_count": len(search_results),
        "search_snippets": snippets,
    }
