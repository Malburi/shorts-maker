---
name: trace
description: 요청/처리 흐름을 진입점부터 끝까지 추적한다. "업로드하면 뭐가 실행돼?", "이 API 어떻게 처리돼?", "쇼츠 생성 흐름 보여줘", "AI 창작 파이프라인 따라가줘", "SSE 진행률이 어떻게 전달돼?", "처리 흐름", "실행 흐름", "trace", "flow of", "흐름 추적", "어떻게 동작해?" 요청 시 트리거. FastAPI 라우트 → 파이프라인(LangGraph/asyncio) → 서비스 → ffmpeg/LLM 까지.
---

# Trace — Shorts Maker 요청 흐름 추적

진입점부터 외부 호출(ffmpeg/LLM/ChromaDB)까지 단계별로 따라간다. 이 프로젝트는 **두 개의 독립 파이프라인**을 가진다 — 먼저 어느 쪽인지 판별한다.

## 0. 파이프라인 판별
- "업로드", "기존 영상", "하이라이트", "쇼츠 추출", `/api/upload`, `/api/youtube` → **업로드 파이프라인** (LangGraph, `backend/pipeline.py`)
- "AI 창작", "처음부터 생성", "인터뷰", "대본", "TTS", `/api/create/*` → **AI Create 파이프라인** (asyncio, `backend/create_pipeline.py`)

## 1. 업로드 파이프라인 추적 순서
1. **진입**: `backend/main.py` 에서 라우트 핸들러 찾기 (`POST /api/upload` 또는 `/api/youtube`). 검증(확장자/500MB/빈파일/URL 정규식) → `Job` 생성 → `BackgroundTasks`로 `run_pipeline` 기동.
2. **그래프**: `backend/pipeline.py`의 `StateGraph` 빌더와 `PipelineState`(TypedDict). 노드 순서:
   `get_duration → extract_audio → transcribe → index_knowledge → select_moments → dispatch_clips → [node_process_clip × N 병렬] → concat_highlight → finalize`
3. **fan-out**: `node_dispatch_clips`가 key moment마다 `Send("node_process_clip", ...)` 발행. 결과는 `Annotated[list, operator.add]` 채널로 병합 (락 없음).
4. **노드 → 서비스 매핑**: 각 `node_*`가 호출하는 `backend/services/*.py` 함수 확인. 서비스는 `_xxx_sync()` + `asyncio.to_thread` 래퍼 패턴.
5. **외부 호출**: transcriber→Whisper, key_moments→Gemini, shorts_maker/caption_maker/thumbnail_gen→ffmpeg, rag→ChromaDB+embeddings.
6. **진행률 → 프론트**: 노드가 `_update(jobs, job_id, ...)`로 jobs dict 갱신 → `GET /api/jobs/{id}/events` SSE가 1초 폴링 → `App.vue` EventSource 수신.

## 2. AI Create 파이프라인 추적 순서
1. **진입**: `backend/routers/create.py` 의 `/api/create/interview` → `/api/create/script` → `/api/create/generate`.
2. interview: 4문항 stateless 왕복 → 완료 시 DuckDuckGo 검색 + gpt-4o outline (`ai_creator.py`).
3. script: gpt-4o 장면별 스크립트.
4. generate: `BackgroundTasks` → `run_create_pipeline` (`create_pipeline.py`). 장면마다 `asyncio.gather(TTS, 이미지)` 병렬 → 클립 합성 → concat → 자막 번인 → `final.mp4`.
5. **진행률**: `_update(create_jobs, ...)` → `GET /api/create/jobs/{id}/events` SSE → `AICreateTab.vue`.

## 3. RAG 챗 추적
`POST /api/jobs/{job_id}/chat` → `rag.query` → 임베딩 → ChromaDB 컬렉션(`j{job_id 무하이픈}`) 검색 → gpt-4o-mini 답변(출처 타임스탬프).

## 출력 형식
- 단계별 `파일:함수(라인)` 체인을 화살표로.
- 분기점(Send fan-out, asyncio.gather, 폴백 체인) 명시.
- 외부 호출 지점에 timeout/retry/폴백 유무 주석 (운영 안정화 관점). `_workspace/index/external_io.json`에 라인별 기록 있음.

상세 의존성은 `_workspace/index/call_graph.json`, `data_flow.json` 참조. 인덱스에 없으면 grep으로 보완.
