# Error Handling Pattern — Shorts Maker

추출 시각: 2026-06-17
샘플 파일 수: 4 (pipeline.py, create_pipeline.py, key_moments.py, main.py)
신뢰도: HIGH (전 파일 통독 — 이 프로젝트 운영 안정화 핵심 영역)

---

## 권장 패턴 (현재 구현된 올바른 패턴)

### 파이프라인 최상위 예외 처리 + 에러 포맷
빈도: 100% (run_pipeline, run_create_pipeline 동일 구조)

```python
# pipeline.py — run_pipeline
async def run_pipeline(job_id, video_path, output_dir, jobs, use_ai_thumbnail=True):
    try:
        await _graph.ainvoke({...})
    except Exception as e:
        job = jobs.get(job_id)
        if job:
            setattr(job, "status", JobStatus.ERROR)
            setattr(job, "step", "오류 발생")
            setattr(job, "error", f"{type(e).__name__}: {e}" if str(e) else type(e).__name__)
            # ← 에러 포맷: "ExceptionType: 메시지" 또는 "ExceptionType"(메시지 없을 때)

# create_pipeline.py — run_create_pipeline
except Exception as e:
    _update(create_jobs, job_id,
            status=JobStatus.ERROR,
            step="오류 발생",
            error=f"{type(e).__name__}: {e}" if str(e) else type(e).__name__)
```

에러 포맷 규칙:
- `f"{type(e).__name__}: {e}"` — 에러 타입 + 메시지 (예: "ValueError: 영상 길이를 읽을 수 없습니다.")
- `type(e).__name__` — 메시지 없을 때 (예: "RuntimeError")
- Job.step은 `"오류 발생"` 고정
- Job.status는 `JobStatus.ERROR`

---

### HTTP 에러 응답 패턴 (라우트 레이어)
빈도: 100% (main.py, routers/create.py 전 검증 지점)

```python
# 모든 HTTP 에러는 한국어 메시지
raise HTTPException(400, "지원하지 않는 형식입니다.")
raise HTTPException(413, "파일 크기는 500MB 이하여야 합니다.")
raise HTTPException(400, "빈 파일입니다.")
raise HTTPException(404, "작업을 찾을 수 없습니다.")
raise HTTPException(400, "잘못된 job_id입니다.")
raise HTTPException(400, "YouTube URL이 아닙니다.")
raise HTTPException(400, "지식 베이스가 아직 준비되지 않았습니다.")
```

---

### Gemini 폴백 체인 + 재시도 (유일한 재시도 구현)
빈도: 단일 구현 (key_moments.py) — 올바른 패턴의 참조 모델

```python
MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]

last_err = None
for model in MODELS:
    for attempt in range(3):
        try:
            response = client.models.generate_content(model=model, ...)
            return json.loads(response.text.strip())
        except Exception as e:
            last_err = e
            if any(x in str(e) for x in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")):
                time.sleep(10 * (attempt + 1))   # 지수 백오프: 10s, 20s, 30s
                continue
            break   # rate-limit 외 에러는 즉시 다음 모델로

raise last_err   # 전체 실패 시 최종 에러 전파
```

판별 기준: "429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE" 문자열 포함 여부.

---

### 썸네일 폴백 (gpt-image-1 실패 → frame 추출)
빈도: 단일 (thumbnail_gen.py)

```python
def _generate_ai_sync(prompt, output_path) -> bool:
    client = _client()
    try:
        resp = client.images.generate(...)
        # 저장 성공 시 return True
        return True
    except Exception:
        return False   # ← 예외 삼킴, False 반환으로 폴백 진입

async def make_thumbnail(..., use_ai=True) -> Path:
    if use_ai:
        success = await generate_ai_thumbnail(...)
        if success:
            return output_path
    # Fallback: frame 추출
    return await extract_frame(clip_path, offset, output_path)
```

---

### TTS 폴백 (edge-tts → OpenAI)
빈도: 단일 (tts_maker.py)

```python
async def generate_tts(text, output_path) -> float:
    try:
        await _tts_edge(text, output_path)
    except Exception:
        await asyncio.to_thread(_tts_openai_fallback, text, output_path)
    return await get_audio_duration(output_path)
```

---

### highlight concat 실패 허용 처리
빈도: 단일 (pipeline.py)

```python
# node_concat_highlight
highlight_reel_url = None
try:
    # concat 시도
    await concat_shorts(clip_paths, highlight_path)
    highlight_reel_url = f"/outputs/{job_id}/highlight_reel.mp4"
except Exception:
    pass  # concat 실패해도 개별 클립은 정상 제공
```

의도: highlight reel은 부가 기능 — 실패해도 메인 결과(개별 클립)에 영향 없음.

---

### web_search graceful 폴백
빈도: 단일 (searcher.py)

```python
async def web_search(query, max_results=6) -> list[dict]:
    try:
        return await asyncio.to_thread(_search_sync, query, max_results)
    except Exception as e:
        logger.warning("web_search failed for %r: %s", query, e)
        return []   # ← 빈 리스트, 파이프라인 계속 진행
```

---

## 안티패턴 (운영 안정화 관점 — 개선 필요)

### 노드별 try/except 부재 — 실패 노드 식별 불가
- 위치: pipeline.py 전 노드 (node_get_duration ~ node_finalize)
- 현황: 노드에 에러 핸들링이 없어 최상위 catch가 받음 → Job.step이 실패 전 마지막 "성공" step을 표시
- 권고 구현:
```python
async def node_transcribe(state: PipelineState) -> dict:
    jobs, job_id = state["jobs"], state["job_id"]
    _update(jobs, job_id, step="① AI 전사 중 (Whisper)...", progress=25)
    try:
        transcript_data = await transcribe(Path(state["audio_path"]))
        ...
        return {"segments": segments, "full_text": full_text}
    except Exception as e:
        _update(jobs, job_id, step=f"전사 실패: {type(e).__name__}")
        raise   # 재 raise — 최상위 catch가 Job.status=ERROR로 마킹
```

---

### OpenAI 호출 timeout/retry 전무 — SSE 무한 대기 위험
- 위치: rag.py, ai_creator.py, thumbnail_gen.py, tts_maker.py, create_pipeline.py
- 위험: Whisper/gpt-4o/embeddings/이미지 생성이 응답 없이 행(hang) → SSE 클라이언트 무한 대기
- 권고 구현:
```python
# backend/services/_openai.py (공통 클라이언트 모듈)
from openai import OpenAI

_client: OpenAI | None = None

def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            timeout=60.0,    # 60초 전체 timeout
            max_retries=2,   # 429/500 자동 재시도 2회
        )
    return _client
```

---

### create_pipeline asyncio.gather fail-fast — 부분 실패 미복구
- 위치: `create_pipeline.py:124` `await asyncio.gather(*[_process_scene(...) for scene in scenes])`
- 위험: 한 장면(TTS/이미지) 실패 → 나머지 성공한 장면 결과 버려짐 + 고아 파일 남음
- 권고 구현:
```python
results = await asyncio.gather(
    *[_process_scene(scene, job_out) for scene in scenes],
    return_exceptions=True   # 부분 실패 허용
)

# 실패 장면 처리
failed = [r for r in results if isinstance(r, Exception)]
if failed:
    logger.warning("장면 %d개 생성 실패: %s", len(failed), failed[0])
    # 성공한 장면만으로 계속 진행하거나, 플레이스홀더로 대체
```

---

### GEMINI_API_KEY os.environ[] 직접 접근 — KeyError 위험
- 위치: `key_moments.py:12` `genai.Client(api_key=os.environ["GEMINI_API_KEY"])`
- 위험: .env에 GEMINI_API_KEY 누락 시 `KeyError: 'GEMINI_API_KEY'` — 불친절한 에러
- 권고 구현:
```python
def _client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY가 설정되지 않았습니다. "
            "프로젝트 루트 .env 파일에 GEMINI_API_KEY=... 를 추가하세요."
        )
    return genai.Client(api_key=api_key)
```

---

### 부분 실패 후 cleanup 없음 — 고아 클립 파일
- 위치: pipeline.py, create_pipeline.py 예외 처리
- 현황: 파이프라인 중간 실패 시 생성된 클립/오디오/이미지가 uploads/{id}/ 또는 create_outputs/{id}/에 남음
- 위험: 디스크 낭비, 불완전한 outputs 디렉토리
- 권고:
```python
except Exception as e:
    _update(jobs, job_id, status=JobStatus.ERROR, step="오류 발생", error=...)
    # 부분 산출물 정리 (선택적)
    import shutil
    if job_out.exists():
        shutil.rmtree(job_out, ignore_errors=True)
```

---

### SSE job 소실 시 조용히 종료
- 위치: `main.py:96` `job = jobs.get(job_id); if not job: break`
- 현황: 서버 재시작으로 jobs dict 소실 → SSE 루프가 break → 프론트는 연결이 끊겼다는 신호 없음
- 권고:
```python
async def event_stream():
    while True:
        job = jobs.get(job_id)
        if not job:
            # 명시적 error 이벤트 전송 후 종료
            yield 'data: {"status":"error","error":"서버가 재시작되었습니다. 페이지를 새로고침하세요."}\n\n'
            break
        ...
```

---

## 에러 처리 계층 요약

```
요청 레이어 (main.py / routers/)
  └─ HTTPException(상태코드, "한국어 메시지")
       ↓
파이프라인 레이어 (pipeline.py / create_pipeline.py)
  └─ 최상위 try/except → Job.status=ERROR, Job.error="ExceptionType: 메시지"
       ↓
서비스 레이어 (services/*.py)
  ├─ 폴백 체인 (thumbnail: AI→frame, TTS: edge→OpenAI, Gemini: 3모델×3회)
  ├─ graceful (searcher: []반환, highlight concat: pass)
  └─ 예외 전파 (OpenAI, ffmpeg returncode != 0: raise RuntimeError)
```

---

## 신규 코드 작성 시 에러 처리 가이드

1. 라우트: 검증 실패 → `raise HTTPException(코드, "한국어 메시지")`
2. 새 파이프라인 노드: 반드시 try/except 추가, 실패 시 `_update(..., step="노드명 실패: ...")` + `raise`
3. 새 외부 서비스 호출 (OpenAI): `get_openai_client()` (timeout=60s, max_retries=2) 사용
4. 새 폴백이 필요한 서비스: `_primary_sync → False 반환` + `if not success: fallback` 구조
5. asyncio.gather 사용 시: `return_exceptions=True` + 부분 실패 명시적 처리
6. env 변수 접근: `os.getenv()` + None 체크 + 명확한 EnvironmentError 메시지
