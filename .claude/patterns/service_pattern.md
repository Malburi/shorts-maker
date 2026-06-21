# Service Pattern — Shorts Maker

추출 시각: 2026-06-17
샘플 파일 수: 9 (backend/services/ 전체 통독)
신뢰도: HIGH (전 서비스 파일 통독, 패턴 매우 일관)

---

## 권장 패턴

### 핵심 패턴: 동기 구현 + async 래핑
빈도: 89% (8/9 서비스 — searcher 제외)

모든 blocking IO (subprocess, OpenAI SDK, Gemini SDK, ChromaDB, edge-tts) 는 동기 구현 함수를 asyncio.to_thread로 래핑하는 방식으로 일관 처리됨.

```python
# 1. 동기 구현 (blocking IO 수행)
def _select_sync(transcript_text: str, total_duration: float) -> list:
    client = _client()
    response = client.models.generate_content(...)
    return json.loads(response.text)

# 2. async 공개 인터페이스 (asyncio.to_thread 래핑)
async def select_key_moments(segments: list, total_duration: float) -> list[KeyMoment]:
    ...
    moments_raw = await asyncio.to_thread(_select_sync, transcript_text, total_duration)
    ...
    return moments
```

실제 사례:
- `key_moments.py`: `_select_sync` → `select_key_moments` (asyncio.to_thread)
- `thumbnail_gen.py`: `_generate_ai_sync` → `generate_ai_thumbnail` (asyncio.to_thread)
- `tts_maker.py`: `_tts_openai_fallback` → `generate_tts` 내부 (asyncio.to_thread)
- `rag.py`: `_index_sync`, `_query_sync` → `index_segments`, `query` (asyncio.to_thread)
- `ai_creator.py`: `_generate_outline_sync`, `_generate_script_sync` → `interview_step`, `generate_script` (asyncio.to_thread)

예외: `searcher.py`의 `web_search`는 DuckDuckGo가 async-native가 아니라 `asyncio.to_thread` 래핑이지만, 내부 `_search_sync`는 별도로 정의됨.

---

### subprocess 헬퍼 `_run`
빈도: 100% (subprocess 사용 파일 모두 동일 패턴)

```python
def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)
```

- 위치: thumbnail_gen.py, tts_maker.py, create_pipeline.py 각각 동일하게 정의
- `capture_output=True` 고정 (stdout/stderr 캡처)
- text 인코딩은 default bytes (decode 필요 시 `.stdout.decode()` 명시)

주의: 중복 정의되어 있음. 공통 util.py로 추출 가능.

---

### OpenAI 클라이언트 헬퍼 `_client`
빈도: 100% (OpenAI 사용 파일 모두 동일 패턴)

```python
def _client() -> OpenAI:
    return OpenAI()   # 매 호출마다 신규 인스턴스
```

- 위치: thumbnail_gen.py:7-8, rag.py 내 인라인(`oai = OpenAI()`), ai_creator.py 내 인라인
- `OpenAI()` 는 `OPENAI_API_KEY` 환경변수 자동 로드
- tts_maker.py는 `_client()` 헬퍼 없이 `client = OpenAI()` 인라인 생성

---

### Gemini 클라이언트 헬퍼
빈도: 단일 (key_moments.py)

```python
def _client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
```

주의: `os.environ["GEMINI_API_KEY"]` — KeyError 위험 (안티패턴 섹션 참고).

---

### LLM 프롬프트 모듈 상수
빈도: 100% (LLM 사용 서비스 전체)

```python
# key_moments.py
SYSTEM_PROMPT = """당신은 SNS 숏폼 콘텐츠 전문가입니다.
...
반드시 아래 JSON 형식으로만 응답하세요 (마크다운 없이):
{"moments": [...]}"""

# ai_creator.py
_OUTLINE_SYSTEM = """\
당신은 유튜브 숏폼 전략가입니다.
...
JSON 외 다른 텍스트는 절대 출력 금지
"""

_SCRIPT_SYSTEM = """\
당신은 유튜브 숏폼 전문 작가입니다.
...
"""
```

규칙:
- 프롬프트는 모듈 상단 상수로 정의 (함수 내 인라인 금지)
- SYSTEM_PROMPT (대문자) 또는 `_OUTLINE_SYSTEM` (언더스코어 프리픽스 + 대문자) 둘 다 사용
- JSON 응답 강제는 두 가지 방식 병용:
  - Gemini: `response_mime_type="application/json"` config + 프롬프트 명시
  - OpenAI: `response_format={"type": "json_object"}` + 프롬프트 명시

---

### Gemini 폴백 체인 (재시도 + 모델 교체)
빈도: 단일 구현 (key_moments.py) — 프로젝트 유일 재시도 로직

```python
MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]

last_err = None
for model in MODELS:               # 3개 모델 순차 시도
    for attempt in range(3):       # 모델당 최대 3회 재시도
        try:
            response = client.models.generate_content(model=model, ...)
            return json.loads(response.text.strip())
        except Exception as e:
            last_err = e
            if any(x in str(e) for x in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")):
                time.sleep(10 * (attempt + 1))   # 10s, 20s, 30s 지수 증가
                continue
            break                  # rate-limit 외 에러는 즉시 다음 모델로

raise last_err   # 모든 모델/시도 실패 시 raise
```

---

### 썸네일 폴백 체인 (gpt-image-1 → frame 추출)
빈도: 단일 (thumbnail_gen.py)

```python
async def make_thumbnail(..., use_ai: bool = True) -> Path:
    if use_ai:
        success = await generate_ai_thumbnail(clip_path, title, reason, output_path)
        if success:
            return output_path

    # Fallback: extract frame at 1/3 into the clip
    offset = clip_duration / 3
    return await extract_frame(clip_path, offset, output_path)
```

`_generate_ai_sync` 내부에서 Exception을 잡아 `return False` — 폴백 진입 보장.

---

### TTS 폴백 체인 (edge-tts → OpenAI TTS)
빈도: 단일 (tts_maker.py)

```python
async def generate_tts(text: str, output_path: Path) -> float:
    try:
        await _tts_edge(text, output_path)      # 무료, 기본
    except Exception:
        await asyncio.to_thread(_tts_openai_fallback, text, output_path)  # 유료, 폴백
    return await get_audio_duration(output_path)
```

---

### ChromaDB singleton 패턴
빈도: 단일 (rag.py)

```python
_chroma: chromadb.ClientAPI | None = None

def _client() -> chromadb.ClientAPI:
    global _chroma
    if _chroma is None:
        _chroma = chromadb.PersistentClient(path=str(_CHROMA_PATH))
    return _chroma
```

다른 서비스의 `_client()`와 달리, ChromaDB만 전역 singleton으로 관리. 이유: PersistentClient 초기화 비용.

컬렉션명 규칙: `f"j{job_id.replace('-', '')}"` (UUID 하이픈 제거 + 'j' 접두어).

---

### 에러 graceful 처리 (searcher.py)
빈도: 단일 — 외부 서비스 graceful 폴백 패턴

```python
async def web_search(query: str, max_results: int = 6) -> list[dict]:
    try:
        return await asyncio.to_thread(_search_sync, query, max_results)
    except Exception as e:
        logger.warning("web_search failed for %r: %s", query, e)
        return []   # ← 빈 리스트 반환, 파이프라인 중단 없음
```

DuckDuckGo는 네트워크 의존적이므로 실패를 `[]`로 graceful 처리.

---

### 한국어 자막 UTF-8-BOM 처리 (caption_maker.py)
빈도: 단일 (caption_maker.py)

```python
# ASS 파일 쓰기 — Windows/ffmpeg 호환 UTF-8-BOM
with open(ass_path, "w", encoding="utf-8-sig") as f:
    f.write(ass_content)
```

`utf-8-sig` = UTF-8 with BOM. Windows 환경 ffmpeg libass에서 한국어 자막 깨짐 방지.

---

### logging 사용
빈도: 낮음 (1/9 서비스 — searcher.py만 사용)

```python
# searcher.py
logger = logging.getLogger(__name__)
logger.warning("web_search failed for %r: %s", query, e)
```

나머지 서비스는 print/logging 없이 예외 전파. 운영 관측성 개선을 위해 logging 도입 권장.

---

## 안티패턴 (피해야 할 패턴)

### OpenAI timeout/retry 전무
- 위치: 모든 OpenAI 호출 (`rag.py`, `ai_creator.py`, `thumbnail_gen.py`, `tts_maker.py`, `create_pipeline.py`)
- 위험: Whisper/gpt-4o/embeddings/이미지 생성이 응답 무한 대기 가능 → SSE 폴링 행(hang)
- 권고:
```python
# 공통 OpenAI 클라이언트 (timeout + 재시도 설정)
from openai import OpenAI
_OAI = OpenAI(timeout=60.0, max_retries=2)
```

### GEMINI_API_KEY os.environ[] 직접 접근
- 위치: `key_moments.py:12` `genai.Client(api_key=os.environ["GEMINI_API_KEY"])`
- 위험: GEMINI_API_KEY 미설정 시 KeyError → 파이프라인 전체 ERROR
- 권고:
```python
api_key = os.getenv("GEMINI_API_KEY") or ""
if not api_key:
    raise EnvironmentError("GEMINI_API_KEY가 설정되지 않았습니다.")
```

### create_pipeline 이미지 생성 폴백 부재
- 위치: `create_pipeline.py:51-52` `_generate_image_sync` — Exception 발생 시 raise 전파
- 위험: asyncio.gather fail-fast로 1개 장면 실패 = 전체 창작 파이프라인 ERROR
- 권고:
```python
async def _generate_image(prompt: str, output_path: Path) -> bool:
    try:
        await asyncio.to_thread(_generate_image_sync, prompt, output_path)
        return True
    except Exception:
        # 폴백: 단색 배경 플레이스홀더 이미지 생성
        return False
```

### OpenAI 클라이언트 매 호출 신규 인스턴스화
- 위치: thumbnail_gen.py:8, tts_maker.py:29, rag.py:51/72, ai_creator.py:81/107
- 현황: `OpenAI()` 를 호출마다 새로 생성
- 위험: 커넥션 풀 미재사용, 약간의 초기화 오버헤드
- 권고: 모듈 레벨 singleton 또는 `_client()` 결과 캐싱

### _run 헬퍼 중복 정의
- 위치: thumbnail_gen.py:12, tts_maker.py:17, create_pipeline.py:21
- 완전히 동일한 함수가 3번 정의됨
- 권고: `backend/services/utils.py` 등 공통 모듈로 추출

### caption_maker 비공개 함수 외부 직접 import
- 위치: `create_pipeline.py:18` `from .services.caption_maker import _write_ass, _burn`
- 위험: 캡슐화 경계 위반. `_write_ass`/`_burn` 시그니처 변경 시 두 파이프라인 동시 영향
- 권고: `caption_maker.py`에 공개 인터페이스 `write_ass()`, `burn_subtitles()` 추가

---

## 신규 서비스 작성 가이드

1. 파일: `backend/services/<도메인명>.py`
2. 구조:
   ```python
   """모듈 docstring — 역할 1-2문장."""
   import asyncio
   ...

   # 모듈 상수 (LLM 프롬프트, 설정값)
   SYSTEM_PROMPT = "..."

   # 내부 헬퍼
   def _run(cmd: list) -> subprocess.CompletedProcess: ...  # subprocess 사용 시
   def _client() -> OpenAI: ...                             # OpenAI 사용 시

   # 동기 구현 (blocking IO)
   def _do_xxx_sync(...) -> ...: ...

   # 공개 async 인터페이스
   async def do_xxx(...) -> ...:
       return await asyncio.to_thread(_do_xxx_sync, ...)
   ```
3. LLM 프롬프트는 모듈 상단 상수로 정의 (대문자 또는 `_XXX_SYSTEM` 패턴)
4. 외부 서비스 실패는 graceful (빈 값 반환) vs 예외 전파를 의도적으로 선택
5. 폴백이 있는 경우 명시적으로 try/except 분기
6. GEMINI_API_KEY 접근 시 `os.getenv()` 사용 + None 체크
