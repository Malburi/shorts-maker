# Route / Endpoint Pattern — Shorts Maker

추출 시각: 2026-06-17
샘플 파일 수: 2 (backend/main.py, backend/routers/create.py)
신뢰도: HIGH (전 엔드포인트 통독, 패턴 일관성 확인)

---

## 권장 패턴

### 라우트 데코레이터 / 네이밍
빈도: 100% (9/9 엔드포인트)

```python
# main.py — app 직접 등록
@app.post("/api/upload")
@app.get("/api/jobs/{job_id}")
@app.get("/api/jobs/{job_id}/events")
@app.delete("/api/history/{job_id}", status_code=204)
@app.get("/api/history")
@app.post("/api/youtube")
@app.post("/api/jobs/{job_id}/chat")
@app.get("/api/health")

# create.py — APIRouter(prefix="/api/create")로 분리
@router.post("/interview")       # → POST /api/create/interview
@router.post("/script")          # → POST /api/create/script
@router.post("/generate")        # → POST /api/create/generate
@router.get("/jobs/{job_id}/events")
@router.get("/jobs/{job_id}")
```

규칙:
- 경로 접두어 `/api/` 필수
- 동사형 경로: `/upload`, `/interview`, `/generate` (명사형 CRUD는 `/history`, `/jobs`)
- 도메인 분리 시 `APIRouter(prefix="/api/create")` + `app.include_router()`
- 라우터 모듈: `backend/routers/create.py` — router 변수 export

---

### 입력 검증 패턴
빈도: HIGH — 검증 실패는 모두 한국어 메시지 HTTPException

```python
# 확장자 화이트리스트 + 크기 + 빈파일
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
MAX_FILE_SIZE = 500 * 1024 * 1024

ext = Path(file.filename or "").suffix.lower()
if ext not in ALLOWED_EXTENSIONS:
    raise HTTPException(400, f"지원하지 않는 형식입니다. ({', '.join(ALLOWED_EXTENSIONS)})")

content = await file.read()
if len(content) > MAX_FILE_SIZE:
    raise HTTPException(413, "파일 크기는 500MB 이하여야 합니다.")
if len(content) == 0:
    raise HTTPException(400, "빈 파일입니다.")

# UUID 경로 파라미터 정규식 검증 (delete_job)
if not re.fullmatch(r"[0-9a-f\-]{36}", job_id):
    raise HTTPException(400, "잘못된 job_id입니다.")

# YouTube URL 정규식 검증
_YT_PATTERN = re.compile(
    r"(youtube\.com/(watch\?.*v=|shorts/)|youtu\.be/)[A-Za-z0-9_\-]+"
)
if not _YT_PATTERN.search(body.url):
    raise HTTPException(400, "YouTube URL이 아닙니다. (youtube.com 또는 youtu.be 링크를 입력하세요)")

# 비즈니스 게이트 (지식베이스 준비 여부)
if not job.has_knowledge:
    raise HTTPException(400, "지식 베이스가 아직 준비되지 않았습니다.")
```

---

### BackgroundTasks 기동 + jobs dict 등록 흐름
빈도: 100% (장시간 작업 전 패턴 — upload, youtube, generate 3곳)

```python
# 1. UUID job_id 생성
job_id = str(uuid.uuid4())

# 2. 모델 인스턴스 생성 + dict 등록 (응답 전 반드시 등록)
job = Job(id=job_id, filename=file.filename or "video")
jobs[job_id] = job                     # ← SSE 폴링이 이 dict를 봄

# 3. BackgroundTasks로 파이프라인 기동
background_tasks.add_task(run_pipeline, job_id, video_path, OUTPUT_DIR, jobs, ai_thumbnail)

# 4. 즉시 반환 (클라이언트가 SSE로 진행 추적)
return {"job_id": job_id}
```

create.py 패턴도 동일:
```python
job = CreateJob(id=job_id, title=body.script.title)
create_jobs[job_id] = job
background_tasks.add_task(run_create_pipeline, job_id, body.script, CREATE_OUTPUT_DIR, create_jobs)
return {"job_id": job_id}
```

---

### SSE 엔드포인트 구조
빈도: 100% (두 SSE 엔드포인트 모두 동일 구조)

```python
@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    async def event_stream():
        while True:
            job = jobs.get(job_id)
            if not job:
                break                                  # job 소실 시 종료
            data = job.model_dump_json()
            yield f"data: {data}\n\n"
            if job.status in (JobStatus.DONE, JobStatus.ERROR):
                break                                  # 완료/오류 시 종료
            await asyncio.sleep(1)                     # 1초 폴링 간격

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",              # nginx 버퍼링 비활성화
        },
    )
```

---

### 에러 응답 컨벤션
빈도: 100% (전 엔드포인트)

- 모든 HTTP 에러는 한국어 메시지
- `raise HTTPException(status_code, "한국어 메시지")` 형식 (2번째 인자 = detail)
- status code: 400(검증), 404(미발견), 413(크기 초과), 204(삭제 성공)
- 파이프라인 내부 예외는 HTTP 에러가 아닌 `Job.error` 필드에 기록

---

### 응답 형식
빈도: 높음

```python
# 생성 — job_id만 반환
return {"job_id": job_id}

# 조회 — Pydantic 모델 직접 반환 (FastAPI가 JSON 직렬화)
return job   # Job 인스턴스

# 삭제 — status_code=204, 응답 바디 없음
@app.delete("/api/history/{job_id}", status_code=204)

# RAG 답변 — dict 직접 반환
return await rag_query(job_id, body.question)
# → {"answer": str, "sources": list}
```

---

### 요청 바디 모델 정의 위치
빈도: 100%

- `backend/models.py` — 전역 공유 모델(Job, CreateJob, KeyMoment 등)
- 라우터 파일 내부 — 해당 라우터 전용 인라인 모델

```python
# main.py 내 인라인 요청 모델 (2곳)
class YoutubeRequest(PydanticBaseModel):
    url: str
    ai_thumbnail: bool = True

class ChatRequest(PydanticBaseModel):
    question: str

# create.py 내 인라인 요청 모델
class InterviewRequest(BaseModel):
    topic: str
    answers: list[AnswerItem] = []
```

---

## 안티패턴 (피해야 할 패턴)

### import를 함수 바디 내부에서 수행
- 위치: `main.py:117` (`delete_job`), `main.py:130` (`get_history`)
- 패턴: `import shutil, re` / `import json as _json` 함수 바디 최상단
- 권고: 모듈 최상단 import로 이동 (성능·가독성)

### 미사용 import
- 위치: `routers/create.py:6` `from ..models import ... ScriptScene, List`
- ScriptScene, List가 라우터에서 직접 사용되지 않음

### CORS 전면 개방
- 위치: `main.py:27` `allow_origins=["*"]`
- 로컬 단일 사용자 도구로서는 허용 가능하나, 운영 노출 시 반드시 오리진 제한 필요

---

## 신규 엔드포인트 작성 가이드

1. 경로는 `/api/[도메인]/[동사 또는 리소스명]` 형식으로 작성
2. 요청 바디가 있으면 라우터 파일 상단에 `class XxxRequest(BaseModel)` 정의
3. 장시간 작업은 반드시 BackgroundTasks + jobs dict 패턴 사용
   - UUID job_id 생성 → dict 등록 → background_tasks.add_task → `{"job_id": job_id}` 반환
4. SSE가 필요하면 `GET /api/.../events` 패턴 그대로 복사 (StreamingResponse + 1초 폴링)
5. 입력 검증 실패는 반드시 `raise HTTPException(코드, "한국어 메시지")`
6. 새 도메인 묶음이면 `backend/routers/` 하위 파일로 분리 후 `app.include_router()` 등록
