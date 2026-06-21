# SSE / Real-time Pattern — Shorts Maker

추출 시각: 2026-06-17
샘플 파일 수: 4 (main.py, routers/create.py, frontend/src/App.vue, frontend/src/components/AICreateTab.vue 참조)
신뢰도: HIGH (전 SSE 구현 통독 — 이 프로젝트 운영 안정화 핵심 영역)

---

## 권장 패턴 (현재 구현)

### 서버 SSE — StreamingResponse 구현
빈도: 100% (2/2 SSE 엔드포인트 완전 동일 구조)

```python
# main.py — 업로드 파이프라인 SSE
@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    async def event_stream():
        while True:
            job = jobs.get(job_id)
            if not job:
                break                                   # job 소실(서버 재시작) 시 종료
            data = job.model_dump_json()
            yield f"data: {data}\n\n"                  # SSE 표준 형식
            if job.status in (JobStatus.DONE, JobStatus.ERROR):
                break                                   # 완료/오류 시 종료
            await asyncio.sleep(1)                      # 1초 폴링 간격

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",                 # nginx 버퍼링 비활성화 (프록시 환경)
        },
    )

# routers/create.py — AI 창작 파이프라인 SSE (동일 구조)
@router.get("/jobs/{job_id}/events")
async def create_job_events(job_id: str):
    if job_id not in create_jobs:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    async def event_stream():
        while True:
            job = create_jobs.get(job_id)
            if not job:
                break
            yield f"data: {job.model_dump_json()}\n\n"
            if job.status in (JobStatus.DONE, JobStatus.ERROR):
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

---

### SSE 페이로드 형식 (models.py 계약)

```python
# Job.model_dump_json() 출력 형식 (업로드 파이프라인)
{
  "id": "uuid-string",
  "filename": "video.mp4",
  "status": "processing",           # pending | processing | done | error
  "step": "① AI 전사 중 (Whisper)...",
  "progress": 25,                   # 0-100 정수
  "error": null,                    # 에러 시 "ExceptionType: 메시지"
  "transcript_preview": "전사 미리보기...",
  "key_moments": [...],             # KeyMoment 리스트
  "shorts": [...],                  # ShortResult 리스트 (완료 시)
  "video_duration": 123.4,
  "completed_at": "2026-06-17T12:00:00",
  "highlight_reel_url": "/outputs/{id}/highlight_reel.mp4",
  "has_knowledge": true
}

# CreateJob.model_dump_json() 출력 형식 (AI 창작 파이프라인)
{
  "id": "uuid-string",
  "title": "영상 제목",
  "status": "processing",
  "step": "② 장면별 영상 클립 합성 중...",
  "progress": 45,
  "error": null,
  "video_url": null,                 # 완료 시 "/create_outputs/{id}/final.mp4"
  "thumbnail_url": null,
  "completed_at": ""
}
```

---

### 프론트엔드 SSE 클라이언트 — App.vue
빈도: 단일 구현 (App.vue:119-131)

```javascript
function startSSE(id) {
  eventSource?.close()                        // 기존 연결 정리
  eventSource = new EventSource(`/api/jobs/${id}/events`)

  eventSource.onmessage = (e) => {
    job.value = JSON.parse(e.data)            // 매 이벤트마다 전체 Job 상태 갱신
    if (job.value.status === 'done' || job.value.status === 'error') {
      eventSource.close()                     // 완료/오류 시 연결 닫기
      historyKey.value++                      // 히스토리 패널 새로고침
    }
  }

  eventSource.onerror = () => eventSource.close()  // 에러 시 닫기 (재연결 없음)
}

onUnmounted(() => eventSource?.close())      // 컴포넌트 언마운트 시 정리
```

---

### progress 값 규약 (pipeline.py 기준)

```
node_get_duration       : 5
node_extract_audio      : 10
node_transcribe         : 25
node_index_knowledge    : 33
node_select_moments     : 42
node_dispatch_clips     : 55
node_concat_highlight   : 88
node_finalize           : 100
```

create_pipeline.py 기준:
```
① TTS + 이미지 생성   : 10
② 장면별 클립 합성    : 45
③ 장면 연결           : 70
④ 자막 합성           : 82
⑤ 마무리             : 95
완료                   : 100
```

step 문자열 형식: 단계 번호 포함 시 `"① 작업명 중..."`, 번호 없을 시 `"작업명 중..."` 또는 `"완료!"`

---

## 안티패턴 (운영 안정화 관점 — 개선 필요)

### 프론트 onerror — 무조건 close, 재연결 없음
- 위치: `App.vue:130` `eventSource.onerror = () => eventSource.close()`
- 현황: 네트워크 순간 단절 시 재연결 없음 → 사용자가 수동 새로고침해야 함
- 권고 구현:
```javascript
let retryCount = 0
const MAX_RETRY = 3

eventSource.onerror = () => {
  eventSource.close()
  if (retryCount < MAX_RETRY) {
    retryCount++
    setTimeout(() => startSSE(id), 2000 * retryCount)  // 2s, 4s, 6s 지수 백오프
  } else {
    // 최대 재시도 초과 — 에러 상태 표시
    job.value = { ...job.value, status: 'error', error: '연결이 끊겼습니다. 페이지를 새로고침하세요.' }
  }
}
```

---

### 서버 재시작 후 job 소실 → 클라이언트 무한 대기
- 위치: `main.py:96` `if not job: break` — break 후 클라이언트에 알림 없음
- 현황: jobs dict는 인메모리 → 서버 재시작 시 소실 → SSE 조용히 종료 → 프론트 "처리 중" 영원히 표시
- 권고 구현:
```python
async def event_stream():
    while True:
        job = jobs.get(job_id)
        if not job:
            # 명시적 에러 이벤트 전송
            yield 'data: {"status":"error","step":"오류 발생","error":"서버가 재시작되었습니다. 새로고침하세요.","progress":0}\n\n'
            break
        ...
```

---

### heartbeat 부재 — 유휴 연결 프록시/방화벽 차단
- 현황: 데이터 없이 대기 중인 구간(예: Whisper 처리 30초)에 이벤트 미발행
- 위험: nginx/CDN/방화벽이 유휴 연결 타임아웃으로 강제 종료
- 권고:
```python
# event_stream() 내부
heartbeat_interval = 15  # 초
last_beat = 0

while True:
    job = jobs.get(job_id)
    if not job:
        break
    data = job.model_dump_json()
    yield f"data: {data}\n\n"
    if job.status in (JobStatus.DONE, JobStatus.ERROR):
        break
    # heartbeat: 15초마다 comment 전송 (SSE 표준 keep-alive)
    await asyncio.sleep(1)
    last_beat += 1
    if last_beat >= heartbeat_interval:
        yield ": heartbeat\n\n"   # SSE comment (클라이언트에서 무시됨)
        last_beat = 0
```

---

### sse-starlette 미사용 — 직접 구현
- 현황: `sse-starlette` 라이브러리가 있음에도 StreamingResponse를 직접 구현
- 현재 직접 구현도 기능상 문제없으나, sse-starlette는 disconnect 감지, 자동 재연결 등 지원
- 권고: 유지 현상 유지 또는 sse-starlette 마이그레이션 (현재 직접 구현이 단순하므로 유지 가능)

---

## 신규 SSE 엔드포인트 작성 가이드

1. 경로: `GET /api/{도메인}/{id}/events` 패턴 유지
2. 함수 구조를 기존 패턴 그대로 복사:
   ```python
   @router.get("/{job_id}/events")
   async def xxx_events(job_id: str):
       if job_id not in xxx_jobs:
           raise HTTPException(404, "작업을 찾을 수 없습니다.")
       async def event_stream():
           while True:
               job = xxx_jobs.get(job_id)
               if not job:
                   break
               yield f"data: {job.model_dump_json()}\n\n"
               if job.status in (JobStatus.DONE, JobStatus.ERROR):
                   break
               await asyncio.sleep(1)
       return StreamingResponse(event_stream(), media_type="text/event-stream",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
   ```
3. 페이로드 모델 변경 시 프론트엔드 onmessage 파서도 함께 수정
4. progress 값은 0-100 범위로 단조 증가 (감소 금지)
5. 완료/에러 시 반드시 status=done/error + break (무한 루프 방지)
6. 운영 안정화 적용 시 heartbeat + onerror 재연결 로직 추가 권장
