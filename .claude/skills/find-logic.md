---
name: find-logic
description: 기능명·키워드·엔드포인트·도메인 용어로 관련 파일·함수·노드를 역방향으로 찾는다. "썸네일 생성 어디서 해?", "자막 번인 코드 찾아줘", "TTS 폴백 어디 있어?", "이 SSE 엔드포인트 코드", "핵심 장면 선택 로직 어디?", "find logic", "어디 있어?", "관련 코드", "관련 파일", "코드 어디에?", "찾아줘", "담당 함수" 요청 시 트리거.
---

# Find Logic — Shorts Maker 역방향 코드 탐색

기능/키워드 → 코드 위치를 찾는다. 인덱스를 먼저 쓰고, 없으면 grep.

## 1. 인덱스 우선
- 심볼/함수: `_workspace/index/symbols.json` (파일별 함수·클래스·노드 + 라인)
- 호출 관계: `_workspace/index/call_graph.json`
- 외부 호출(LLM/ffmpeg/ChromaDB) 위치: `_workspace/index/external_io.json`
- env/설정 분기: `_workspace/index/env_branches.json`
- 데드 코드 후보: `_workspace/index/dead_code.json`

## 2. 레이어별 탐색 지도
| 찾는 대상 | 보는 곳 |
|-----------|---------|
| 라우트/엔드포인트 | `backend/main.py`, `backend/routers/create.py` |
| 업로드 파이프라인 노드 | `backend/pipeline.py` (`node_*` 네이밍) |
| AI 창작 파이프라인 | `backend/create_pipeline.py` |
| 도메인 로직 (전사/장면/쇼츠/자막/썸네일/RAG/창작/검색/TTS) | `backend/services/*.py` |
| 스키마/모델 | `backend/models.py` (Pydantic v2 + Enum) |
| 프론트 화면/탭/SSE | `frontend/src/App.vue`, `frontend/src/components/*.vue` |

## 3. 키워드 → 파일 힌트
- 전사/Whisper → `services/transcriber.py`
- 핵심 장면/Gemini/폴백 → `services/key_moments.py`
- 9:16 크롭/페이드/concat → `services/shorts_maker.py`
- ASS 자막/번인/UTF-8-BOM → `services/caption_maker.py`
- AI 썸네일/프레임 추출 → `services/thumbnail_gen.py`
- RAG/ChromaDB/임베딩 → `services/rag.py`
- 인터뷰/outline/대본/DuckDuckGo → `services/ai_creator.py`, `services/searcher.py`
- TTS/edge-tts/voice → `services/tts_maker.py`
- SSE 진행률 → `main.py`(`/events`) + `App.vue`/`AICreateTab.vue` (EventSource)

## 4. grep 전략 (인덱스 미스 시)
- 함수/노드 정의: `def node_`, `def _.*_sync`, `async def`
- 외부 호출: `OpenAI(`, `genai`, `ffmpeg`, `ffprobe`, `chromadb`, `edge_tts`, `ddgs`
- 라우트: `@app.post`, `@app.get`, `@router.post`
- SSE: `EventSource`, `StreamingResponse`, `text/event-stream`

## 출력 형식
후보 `파일:라인 — 역할` 목록 + 가장 가능성 높은 진입점 1개를 표시. 공유 함수(여러 파이프라인에서 호출)는 별도 표시.
