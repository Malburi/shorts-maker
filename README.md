# Shorts Maker

AI로 9:16 세로 유튜브 쇼츠를 만드는 도구. 두 가지 모드를 제공합니다.

- **업로드 모드**: 기존 가로 영상을 업로드하면 핵심 장면을 추출해 자막·썸네일이 포함된 세로 쇼츠를 만듭니다. 세로 변환은 **스마트 크롭**(OpenCV로 주 피사체를 자동 감지: 얼굴 → 움직임 → 세일런시)으로 인물·스포츠 공·게임 캐릭터·주요 액션을 따라가며, 뚜렷한 피사체가 없으면 **레터박스**(원본 전체 + 위아래 검은 여백, 잘림 없음)로 폴백합니다.
- **AI 창작 모드**: **프롬프트 한 줄**로 완성 영상을 생성합니다. 프롬프트 → 웹 검색 → 일관된 대본(통합 `visual_style` + 장면별 나레이션/묘사) → **Nano Banana 기준 이미지 + 장면별 레퍼런스 이미지** → **Veo 이미지→영상** + TTS + 자막 → 최종 영상.

## 처리 흐름

**업로드 모드**
```
영상 업로드
  → ffmpeg 오디오 추출
  → OpenAI Whisper 전사 (타임스탬프)
  → Gemini 2.5-flash 핵심 장면 3~5개 선정
  → ChromaDB 인덱싱 (RAG Q&A용)
  → ffmpeg 9:16 스마트 크롭 / 레터박스 클립 생성 (병렬)
  → 하이라이트 릴 concat
  → 결과 갤러리 + 챗(Q&A) 표시
```

**AI 창작 모드**
```
프롬프트 한 줄
  → 웹 검색(DuckDuckGo) + GPT-4o 대본 (visual_style + 장면)
  → Nano Banana 기준 이미지 생성
  → 장면별: TTS(edge-tts) + Nano Banana 이미지(기준 레퍼런스)
  → 장면별: Veo 이미지→영상 (실패 시 Ken Burns 정지영상 폴백)
  → concat → ASS 자막 번인 → 최종 영상
```

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 백엔드 | FastAPI + Python 3.11+ |
| 파이프라인 | LangGraph (업로드) / asyncio (창작) |
| 프론트엔드 | Vue 3 + Tailwind CSS + Vite |
| 영상 처리 | ffmpeg (PATH 등록 필요, libass 포함 빌드) |
| AI | OpenAI Whisper/GPT-4o/gpt-image-1 · Google Gemini 2.5-flash · Nano Banana(`gemini-2.5-flash-image`) · Veo(`veo-3.1-fast-generate-preview`) · edge-tts |
| 비전 | OpenCV (스마트 크롭용 피사체 감지) |
| 벡터 DB | ChromaDB (로컬, RAG Q&A) |
| 실시간 | Server-Sent Events (SSE) |

## 사전 요구사항

- Python 3.11+
- Node.js 18+
- `ffmpeg` (PATH에 등록, `libass` 지원 빌드 — Windows는 gyan.dev 빌드 권장)
- 프로젝트 루트에 `.env` 파일:
  ```
  OPENAI_API_KEY=sk-...
  GEMINI_API_KEY=...
  ```
  > `GEMINI_API_KEY`는 핵심 장면 선정과 Nano Banana 이미지에 필요합니다. **Veo 영상 생성은 유료(결제) Gemini 등급이 필요**하며, 없으면 창작 모드의 각 장면이 자동으로 Ken Burns 정지영상으로 폴백됩니다.

## 설치

```powershell
# 백엔드
pip install -r backend/requirements.txt

# 프론트엔드
cd frontend
npm install
```

## 실행

```powershell
# 방법 1: 통합 스크립트
.\start.ps1

# 방법 2: 수동
# 터미널 1 - 백엔드
uvicorn backend.main:app --reload

# 터미널 2 - 프론트엔드
cd frontend
npm run dev
```

브라우저에서 http://localhost:5173 접속 (포트가 사용 중이면 Vite가 5174 등으로 띄웁니다).

## API

**업로드 모드**

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/upload` | 영상 업로드 → job_id 반환 |
| GET | `/api/jobs/{id}` | 작업 상태 조회 |
| GET | `/api/jobs/{id}/events` | SSE 실시간 진행 스트림 |
| GET | `/api/history` | 지난 작업 목록 |
| POST | `/api/jobs/{id}/chat` | 인덱싱된 영상에 대한 RAG Q&A |
| GET | `/outputs/{id}/...` | 생성된 쇼츠/썸네일 |

**AI 창작 모드**

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/create/script` | 프롬프트 한 줄 → 일관된 대본 |
| POST | `/api/create/generate` | 대본 → 영상 생성 시작, job_id 반환 |
| GET | `/api/create/jobs/{id}` | 창작 작업 상태 조회 |
| GET | `/api/create/jobs/{id}/events` | SSE 실시간 진행 스트림 |
| GET | `/create_outputs/{id}/...` | 생성된 영상/썸네일 |

## 비용 주의

- Whisper: ~$0.006/분
- GPT-4o / GPT-4o-mini: 저렴
- gpt-image-1 (업로드 썸네일): 약 $0.011/장 — 업로드 화면에서 끄면 프레임 추출로 대체
- Nano Banana 이미지: 장면당 1~2장
- **Veo 영상 생성은 비용이 크고 느립니다**(장면당 수십 초~수 분). 테스트 시 장면 수를 줄이세요. 결제 미설정 시 Ken Burns 폴백으로 동작합니다.

## 비고

- 로컬 단일 사용자 도구를 전제로 합니다 (CORS 전면 개방, 인증 없음).
- 자막은 한국어/Windows 호환을 위해 UTF-8-BOM ASS로 작성되며, Whisper/TTS는 한국어(`ko`) 기준입니다.
- 런타임 산출물(`create_outputs/`, `chroma_db/`, `frontend/dist/`)은 git에서 제외됩니다.
