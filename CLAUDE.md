# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

AI-powered YouTube Shorts generator with two modes:
- **Upload mode**: Analyzes an existing video, extracts key moments, creates 9:16 vertical clips with captions and thumbnails. Vertical conversion uses **smart crop** that auto-detects the subject (face → motion → saliency, so it follows a person, a sports ball, a game character, or the main action) with a **letterbox fallback** (full frame + black bars, no cropping) when no clear subject is found.
- **AI Create mode**: Generates a complete short from a **single free-text prompt** — prompt → web search → one consistent script (unified `visual_style` + per-scene narration/description) → **Nano Banana anchor image + per-scene reference images** → **Veo image-to-video** + TTS + captions → final video

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI + Python 3.11+ |
| Pipeline orchestration | LangGraph (StateGraph + Send API) |
| Frontend | Vue 3 + Tailwind CSS + Vite |
| Video processing | ffmpeg (must be in PATH) |
| AI | OpenAI Whisper/GPT-4o/gpt-image-1 (upload thumbnails); Google Gemini 2.5-flash (key moments), **Nano Banana `gemini-2.5-flash-image`** (create images), **Veo `veo-3.1-fast-generate-preview`** (create video); edge-tts (Microsoft Azure, free) |
| Vision | OpenCV (`opencv-python`) — face detection for smart vertical crop |
| Vector DB | ChromaDB (local, for RAG Q&A) |
| Real-time | Server-Sent Events (SSE) |

## Running the App

**Automated (Windows):**
```powershell
.\start.ps1
```
Starts backend on `http://localhost:8000`, frontend on `http://localhost:5173`, opens browser.

**Manual (two terminals):**
```powershell
# Terminal 1
cd backend && uvicorn main:app --reload

# Terminal 2
cd frontend && npm run dev
```

**Prerequisites:**
- `ffmpeg` in PATH
- `.env` at project root with `OPENAI_API_KEY` and `GEMINI_API_KEY`
- `pip install -r backend/requirements.txt` and `npm install` in `frontend/`

## Architecture

### Backend (`backend/`)

**Entry point:** `main.py` — FastAPI app with these routes:
- `POST /api/upload` — accepts video, creates Job, starts background pipeline
- `GET /api/jobs/{id}/events` — SSE stream (0.5s updates) for upload pipeline
- `GET /api/jobs/{id}` — job status/result
- `GET /api/history` — list past jobs
- `POST /api/jobs/{job_id}/chat` — RAG Q&A against an indexed video (note: earlier docs said `POST /api/chat`; the real route is job-scoped)
- Router `routers/create.py` — AI creation endpoints: `POST /api/create/script` (single prompt → consistent script), `POST /api/create/generate`, `GET /api/create/jobs/{id}/events`, `GET /api/create/jobs/{id}`. (The old `/api/create/interview` + outline step were removed — input is now one free-text prompt.)

**Upload pipeline:** `pipeline.py` — LangGraph `StateGraph` with `PipelineState` (TypedDict). Key pattern: `node_dispatch_clips` fans out via `Send("node_process_clip", ...)` for each key moment; results accumulate via `Annotated[list, operator.add]` (parallel-safe). Node sequence:

```
get_duration → extract_audio → transcribe → index_knowledge → select_moments
  → dispatch_clips → [node_process_clip × N in parallel] → concat_highlight → finalize
```

**AI Create pipeline:** `create_pipeline.py` — asyncio-based, no LangGraph. Stages: (0) generate one **anchor image** from `script.visual_style`; (1) per scene, `asyncio.gather()` runs TTS + Nano Banana image generation **using the anchor as a reference** (style/character/setting consistency); (2) per scene, **Veo image-to-video** (concurrency-limited via `asyncio.Semaphore`) — on Veo failure/timeout it falls back to a **Ken Burns (zoompan) still-image clip**; (3) concat → (4) ASS captions burn-in → (5) thumbnail = first scene image. Veo audio is discarded; TTS is mapped in via ffmpeg `-map 0:v -map 1:a`. Clip length is matched to the TTS narration (`tpad` clones the last frame to extend short Veo clips, `-t` trims).

**Services (`backend/services/`):**

| File | Responsibility |
|------|---------------|
| `transcriber.py` | ffmpeg audio extract → OpenAI Whisper (Korean, with timestamps) |
| `key_moments.py` | Gemini 2.5-flash → 3-5 key moments with fallback chain (2.0-flash → flash-latest) |
| `smart_crop.py` | OpenCV multi-tier subject detection over sampled frames → smart 9:16 crop x-offset. Tiers: face (Haar frontal+profile) → motion (frame-diff column centroid, class-agnostic: ball/character/action) → saliency (Laplacian edge-density centroid). Returns `None` (caller letterboxes) only when no clear subject |
| `shorts_maker.py` | ffmpeg 9:16 (1080×1920): smart crop when `smart_crop` finds a subject, else letterbox (scale+pad); fade in/out; `concat_shorts` clip concat |
| `caption_maker.py` | ASS subtitle generation + ffmpeg burn-in; UTF-8-BOM for Korean/Windows |
| `thumbnail_gen.py` | gpt-image-1 AI thumbnail or fallback to frame extraction (upload mode only) |
| `veo_maker.py` | Nano Banana (`gemini-2.5-flash-image`) 9:16 image gen (optional reference image for consistency) + Veo (`veo-3.1-fast-generate-preview`) image-to-video (long-running op polling, 6-min timeout); `pick_duration()` chooses 4/6/8s |
| `rag.py` | ChromaDB + text-embedding-3-small; GPT-4o-mini for answers |
| `ai_creator.py` | Single prompt → DuckDuckGo search → GPT-4o `generate_script(prompt)` returning unified `visual_style` + per-scene narration/image_prompt (no more interview/outline) |
| `tts_maker.py` | edge-tts primary (ko-KR-SunHiNeural) → OpenAI TTS-1-hd fallback |

**Models:** `models.py` — Pydantic v2: `Job`, `JobStatus`, `KeyMoment`, `ShortResult`, `CreateJob`, `ScriptData` (now includes `visual_style`), `ScriptScene`. (`ContentOutline` is now dead code — left in place but no longer used after the interview/outline removal.)

### Frontend (`frontend/src/`)

`App.vue` — 3-tab layout: Upload, AI Create, History. Manages SSE connections globally.

Key components:
- `UploadZone.vue` — drag-drop file input
- `ProgressPanel.vue` — SSE-driven progress bar + step text
- `ResultsGrid.vue` — shows shorts with inline player, thumbnail toggle (AI vs frame), download buttons
- `AICreateTab.vue` — phases: `input` (single prompt) → `preview` (edit unified `visual_style` + scenes) → `generating` → `done`
- `ChatPanel.vue` — RAG Q&A UI

### Output Structure

```
uploads/{job_id}/          # upload mode input + outputs
create_outputs/{job_id}/   # AI create mode outputs
chroma_db/                 # ChromaDB persistent storage
```

## Key Design Decisions

**LangGraph Send() + operator.add**: Enables automatic parallel processing — each clip is a separate graph invocation but results safely merge into shared state without locks.

**SSE over WebSocket**: Simpler server-side (`sse-starlette`), browser auto-reconnects, no handshake — sufficient for one-directional progress updates.

**ffmpeg in `asyncio.to_thread()`**: All ffmpeg subprocesses run in thread pool to avoid blocking the FastAPI event loop.

**Fallback chains**: Gemini (rate-limit retry across model versions), TTS (edge-tts free → OpenAI paid), upload thumbnail (gpt-image-1 → frame extraction), **vertical conversion (smart crop → letterbox)**, **create scene video (Veo → Ken Burns still-image clip)**, **create anchor image (anchor → per-scene independent images if anchor gen fails)**. Always check cost before calling gpt-image-1 with `quality="high"`. **Veo is expensive** (paid Gemini billing required) and slow (minutes per clip); concurrency is capped via `asyncio.Semaphore(VEO_CONCURRENCY)`.

**Korean language specifics**: ASS subtitles written with UTF-8-BOM (`utf-8-sig`). Whisper called with `language="ko"`. TTS uses `ko-KR-SunHiNeural`.

## Important Gotchas

- `GEMINI_API_KEY` is read in `key_moments.py` and `veo_maker.py` via `os.environ` — must be in `.env` at project root (loaded via `python-dotenv` in `main.py`)
- **Veo `generate_audio` is NOT supported on the Gemini Developer API** (`genai.Client(api_key=...)`) — it only works in Vertex/Enterprise mode and raises `ValueError` if passed. So `veo_maker` omits it; Veo's own generated audio is simply discarded in ffmpeg (`-map 0:v`) and TTS is used instead.
- **Veo requires paid Gemini billing.** Without it every scene's Veo call fails and the pipeline degrades to Ken Burns still-image clips (no error — just no motion).
- `smart_crop.py` needs `opencv-python` (+numpy); detection is multi-tier (face → motion → saliency, all class-agnostic, no extra model downloads). If it can't import or no clear subject is found, upload-mode vertical conversion letterboxes instead of cropping.
- ffmpeg must support `libass` for subtitle burn-in; Windows builds from gyan.dev include it
- `create_pipeline.py` is a standalone module (not imported by main.py directly) — the create router calls it via `asyncio.create_task()`
- ChromaDB persists to `chroma_db/` relative to where uvicorn runs (i.e., `backend/` dir); deleting it clears all RAG indexes
- The `docs/study_guide.md` is a comprehensive architecture reference (1300+ lines) — useful before making systemic changes

## 자동 워크플로우

Claude는 아래 상황에 해당하는 스킬을 우선 사용한다. 스킬은 `.claude/skills/`에, 호출되는 공통 에이전트는 harness-ito 플러그인이 제공한다.

| 상황 | 스킬 |
|------|------|
| 요청 흐름 추적 (업로드/창작 파이프라인, API → 서비스 → ffmpeg/LLM 따라가기) | trace |
| 로직/기능 위치 탐색 (역방향: 엔드포인트·키워드 → 코드) | find-logic |
| 기본 신규 파일 체크리스트 | scaffolder |
| 변경 영향도 분석 (함수/노드/엔드포인트 수정 전) | analyze-impact |
| 안전한 변경 진행 (사전 영향 → 적용 → 사후 안전성) | safe-modify |
| 컨벤션 따라 신규 기능/서비스 생성 | scaffold-feature |

> RDB가 없어 `review-sql`은 의도적으로 생성하지 않았다. 마이그레이션 요구가 없어 `plan-migration`도 생략했다 (필요 시 harness-ito의 `plan-migration` 스킬 직접 호출 가능).

## 작업 시 주의사항

목표 우선순위는 **코드 구조 이해 + 운영 안정화**이며, 특히 폴백 체인·에러 핸들링·SSE 안정성이 핵심이다. 아래는 analyzer가 코드 라인 단위로 확인한 운영 안정화 핵심 발견 (우선순위순) 이다.

1. **requirements.txt 누락 의존성 (배포 치명, 최우선)**: `google-genai`, `opencv-python`는 이제 `backend/requirements.txt`에 추가됨. 그러나 코드가 import하는 `langgraph`, `langchain`, `chromadb`, `ddgs`는 여전히 빠져 있어 `pip install -r backend/requirements.txt`만으로는 실행 불가하다. 실제 가상환경 `pip freeze`로 나머지도 버전 고정 권장.
2. **폴백 체인 (창작 비주얼)**: `create_pipeline.py`의 장면 영상 생성은 `Veo → Ken Burns(정지이미지 zoompan)` 폴백을 갖춰 일부 장면 실패가 전체 작업을 죽이지 않는다(`_make_scene_clip`의 try/except). 단, **이미지 생성(Nano Banana)** 자체는 여전히 stage 1의 `asyncio.gather`가 fail-fast — 한 장면 이미지 실패는 작업 전체 ERROR. 기준 이미지(anchor) 생성 실패는 레퍼런스 없이 진행(폴백)한다.
3. **OpenAI 호출 timeout/retry 전무**: Whisper/gpt-4o/embeddings/이미지 호출 모두 무제한 대기 가능 → 행(hang) 시 SSE 폴링이 영원히 진행 중 표시. 재시도/백오프는 `key_moments.py`(Gemini)에만 존재. `OpenAI(timeout=..., max_retries=...)` 공통 클라이언트 도입 권장.
4. **GEMINI_API_KEY KeyError 위험**: `key_moments.py`에서 `os.environ[...]` 직접 인덱싱 → 미설정 시 불친절한 KeyError로 파이프라인 ERROR. `os.getenv` + 기동 시 사전 검증 권장.
5. **SSE 안정성**: 프론트 EventSource(App.vue, AICreateTab.vue)가 `onerror`에서 무조건 `close()`만 하고 재연결이 없다. 서버는 jobs dict를 폴링하므로 서버 재시작으로 job이 dict에서 사라지면 스트림이 조용히 break → 프론트는 영원히 진행 중. heartbeat/타임아웃/재연결 로직 부재.
6. **에러 핸들링 일관성**: 노드별 try/except 없이 `run_pipeline` 최상위에서만 포괄 catch → 어느 노드가 실패했는지 사용자 메시지에 미반영. `create_pipeline`도 단일 try. 부분 실패 cleanup(고아 클립 파일 정리) 로직 없음.
7. **인메모리 상태 휘발**: `jobs`/`create_jobs` dict는 서버 재시작 시 소실. 진행 중 작업 추적 불가 (히스토리만 `meta.json` glob로 복구).

추가 주의:
- **공유 핵심 함수**: `shorts_maker.concat_shorts`, `thumbnail_gen.extract_frame`, `caption_maker._write_ass/_burn`는 업로드+창작 두 파이프라인이 공유한다. `create_pipeline`이 `caption_maker`의 비공개 함수(`_write_ass`, `_burn`)를 직접 import하므로 시그니처 변경 시 양쪽 동시 영향. (`shorts_maker.make_short`는 `smart_crop`을 호출하므로 업로드 전용.)
- **Veo 비용/지연**: `veo_maker.VIDEO_MODEL`/`VEO_RESOLUTION`/`VEO_CONCURRENCY`로 등급·해상도·동시성 조절. Veo는 장면당 수십 초~수 분, 비용도 크므로 테스트 시 장면 수를 줄여서(예: 1~2개) 검증할 것.
- **테스트 전무**: 회귀 안전망이 없다. 변경 시 `safe-modify` 워크플로우로 영향도 확인 + 테스트 골격 생성 권장.
- **CORS 전면 개방**(`allow_origins=["*"]`) + 인증 없음 + 무제한 비용 LLM/이미지 호출 → 운영 노출 시 비용/보안 가드 필요. 로컬 단일 사용자 도구 전제.
- **챗 엔드포인트 경로**: 실제는 `POST /api/jobs/{job_id}/chat` (이전 문서의 `/api/chat`는 드리프트, 위에서 수정됨).

## 변경 이력

| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-06-17 | harness 표준 섹션 추가(자동 워크플로우/작업 주의사항/변경 이력), 챗 엔드포인트 경로 정정, 운영 안정화 핵심 발견 7건 반영 | CLAUDE.md + .claude/* | harness-fin 적용 (기존 영문 아키텍처 문서 보존) |
| 2026-06-21 | 업로드 세로 변환을 스마트 크롭(OpenCV 다단계: 얼굴→움직임→세일런시)+레터박스 폴백으로 전환 | `services/smart_crop.py`(신규), `shorts_maker.py`, `requirements.txt` | 센터 크롭 잘림 해결 + 스포츠 공·게임 캐릭터 등 장르 무관 주 피사체 추적 |
| 2026-06-21 | 창작 모드를 Nano Banana 이미지 + Veo 영상 생성으로 교체(gpt-image-1 정지이미지 폐기) | `services/veo_maker.py`(신규), `create_pipeline.py`, `requirements.txt` | 정지이미지 대신 실제 모션 영상 생성 |
| 2026-06-21 | 창작 입력을 4질문 인터뷰→단일 프롬프트로 단순화, 기준 이미지(anchor)+레퍼런스로 장면 간 일관성 확보 | `ai_creator.py`, `routers/create.py`, `models.py`(`visual_style`), `AICreateTab.vue` | 쓸데없는 질문 제거 + 영상 통일감 향상 |
