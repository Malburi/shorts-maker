# Shorts Maker 완전 분석 — 발표·면접 대비 공부 자료

> 이 문서는 Shorts Maker 시스템을 **누구에게든 자신 있게 설명**할 수 있도록
> 설계부터 코드 한 줄까지 완전히 풀어쓴 자료입니다.

---

## 목차

1. [한 문장 요약 & 엘리베이터 피치](#1-한-문장-요약--엘리베이터-피치)
2. [시스템 전체 구조 (Big Picture)](#2-시스템-전체-구조-big-picture)
3. [핵심 개념 1 — LangGraph 파이프라인](#3-핵심-개념-1--langgraph-파이프라인)
4. [핵심 개념 2 — SSE 실시간 스트리밍](#4-핵심-개념-2--sse-실시간-스트리밍)
5. [핵심 개념 3 — RAG (영상 질의응답)](#5-핵심-개념-3--rag-영상-질의응답)
6. [핵심 개념 4 — AI 창작 파이프라인](#6-핵심-개념-4--ai-창작-파이프라인)
7. [핵심 개념 5 — 비디오 처리 (ffmpeg)](#7-핵심-개념-5--비디오-처리-ffmpeg)
8. [핵심 개념 6 — TTS (음성 합성)](#8-핵심-개념-6--tts-음성-합성)
9. [핵심 개념 7 — AI 이미지 생성](#9-핵심-개념-7--ai-이미지-생성)
10. [프론트엔드 아키텍처](#10-프론트엔드-아키텍처)
11. [백엔드 API 전체 목록](#11-백엔드-api-전체-목록)
12. [데이터 모델 (Models)](#12-데이터-모델-models)
13. [코드 상세 분석 (파일별)](#13-코드-상세-분석-파일별)
14. [예상 질문 & 모범 답변](#14-예상-질문--모범-답변)
15. [기술 선택 이유 (Why not X?)](#15-기술-선택-이유-why-not-x)
16. [시스템 한계 & 개선 방향](#16-시스템-한계--개선-방향)

---

## 1. 한 문장 요약 & 엘리베이터 피치

### 한 문장
> "영상을 업로드하거나 주제를 입력하면, AI가 핵심 장면 선별·9:16 변환·자막·나레이션·썸네일을 전부 자동 생성하는 풀스택 쇼츠 제작 플랫폼입니다."

### 엘리베이터 피치 (30초 버전)
```
이 시스템은 두 가지 방식으로 쇼츠를 만듭니다.

첫째, 기존 영상을 올리면 Google Gemini AI가 전사 텍스트를 분석해서
임팩트 높은 장면을 자동으로 골라 9:16으로 잘라주고, 자막과 썸네일까지 붙여줍니다.

둘째, 주제만 입력하면 AI 인터뷰 → 기획안 → 대본 순서로 단계별로 확인받으면서
나레이션 음성과 AI 이미지를 합성해 처음부터 영상을 만들어 줍니다.

백엔드는 FastAPI + LangGraph, 프론트는 Vue 3으로 구성했고,
생성 과정을 SSE로 실시간으로 보여줍니다.
```

---

## 2. 시스템 전체 구조 (Big Picture)

### 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│                       사용자 브라우저                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  업로드 탭    │  │  AI 창작 탭  │  │   히스토리 탭     │  │
│  │ (App.vue)    │  │(AICreateTab) │  │ (HistoryPanel)   │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │  SSE 실시간 스트리밍      REST API         │        │
└─────────┼──────────────────────────────────────────────────-┘
          │  HTTP / EventSource
┌─────────▼──────────────────────────────────────────────────┐
│                    FastAPI 서버 (main.py)                    │
│  /api/upload   /api/youtube   /api/jobs/{id}/events   /api/create/...     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  BackgroundTasks → 파이프라인 비동기 실행             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────┐   ┌───────────────────────────┐   │
│  │  pipeline.py         │   │  create_pipeline.py        │   │
│  │  (LangGraph 기반)     │   │  (asyncio 기반)            │   │
│  └──────────────────────┘   └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                      서비스 레이어                            │
│  key_moments.py   rag.py   ai_creator.py   searcher.py      │
│  tts_maker.py   thumbnail_gen.py   shorts_maker.py          │
│  caption_maker.py   transcriber.py                          │
└────────────────────────────┬────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   ┌────────────┐    ┌───────────────┐   ┌──────────────┐
   │ Google     │    │  OpenAI API   │   │   ffmpeg     │
   │ Gemini API │    │ GPT-4o/Whisper│   │  (로컬 바이너리)│
   │ (장면 선정) │    │ TTS/이미지     │   │  (비디오 처리) │
   └────────────┘    └───────────────┘   └──────────────┘
                             │
                      ┌──────▼──────┐
                      │  ChromaDB   │
                      │ (로컬 벡터DB)│
                      └─────────────┘
```

### 폴더 구조
```
shorts-maker/
├── backend/
│   ├── main.py                 ← FastAPI 앱 진입점
│   ├── pipeline.py             ← 영상 분석 파이프라인 (LangGraph)
│   ├── create_pipeline.py      ← AI 창작 파이프라인 (asyncio)
│   ├── models.py               ← Pydantic 데이터 모델
│   ├── routers/
│   │   └── create.py           ← AI 창작 전용 API 라우터
│   └── services/
│       ├── transcriber.py      ← Whisper 음성 인식
│       ├── key_moments.py      ← Gemini AI 핵심 장면 선정
│       ├── shorts_maker.py     ← ffmpeg 클립 편집
│       ├── caption_maker.py    ← ASS 자막 생성/번인
│       ├── tts_maker.py        ← Microsoft/OpenAI TTS
│       ├── thumbnail_gen.py    ← AI 썸네일 생성
│       ├── rag.py              ← ChromaDB 질의응답
│       ├── ai_creator.py       ← 인터뷰·기획안·대본 AI
│       └── searcher.py         ← DuckDuckGo 웹 검색
├── frontend/
│   └── src/
│       ├── App.vue             ← 메인 컨테이너 (3탭)
│       └── components/
│           ├── ResultsGrid.vue ← 쇼츠 결과 그리드
│           ├── AICreateTab.vue ← AI 창작 5단계 UI
│           ├── ChatPanel.vue   ← RAG 채팅 UI
│           ├── UploadZone.vue  ← 파일 업로드 영역
│           └── ProgressPanel.vue ← 진행률 표시
├── chroma_db/                  ← ChromaDB 로컬 벡터 저장소
├── outputs/                    ← 생성된 쇼츠 저장
└── create_outputs/             ← AI 창작 결과물 저장
```

---

## 3. 핵심 개념 1 — LangGraph 파이프라인

### LangGraph란?
LangGraph는 **AI 워크플로우를 '노드와 엣지로 이루어진 그래프'로 표현**하는 라이브러리입니다.
각 노드는 함수(작업 단위)이고, 엣지는 "이 작업이 끝나면 저 작업으로 가라"는 규칙입니다.

```
일반 코드:                      LangGraph:
A → B → C → D                 A → B → [C, D, E 동시] → F
(순차)                         (조건부 병렬 팬아웃 가능)
```

### 이 프로젝트에서의 LangGraph 그래프

```
START
  │
  ▼
node_check_duration (영상 길이 확인)
  │
  ▼
node_extract_audio (ffmpeg으로 오디오 추출)
  │
  ▼
node_transcribe (OpenAI Whisper로 텍스트 변환)
  │
  ▼
node_index_rag (ChromaDB에 전사 텍스트 저장)
  │
  ▼
node_select_moments (Gemini AI가 핵심 장면 3~5개 선정)
  │
  ▼ (조건부 팬아웃 — 핵심 장면 수만큼 분기)
  ├── Send("node_process_clip", clip_0) ──┐
  ├── Send("node_process_clip", clip_1) ──┤
  └── Send("node_process_clip", clip_2) ──┘
                                          │ (모두 완료 후 합류)
                                          ▼
                                  node_make_highlight (하이라이트 릴 합성)
                                          │
                                          ▼
                                  node_save_meta (메타데이터 저장)
                                          │
                                          ▼
                                         END
```

### Send() API — 핵심 병렬화 메커니즘

```python
# pipeline.py 내부 코드 해설

def dispatch_clips(state: PipelineState):
    """
    핵심 장면이 3개라면 Send()를 3번 호출 → 3개 노드가 병렬 실행됨
    핵심 장면이 5개라면 Send()를 5번 호출 → 5개 노드가 병렬 실행됨
    """
    return [
        Send("node_process_clip", {
            "clip": moment,          # 각 클립 정보만 다름
            "job_id": state["job_id"],  # 나머지 상태는 공유
            "video_path": state["video_path"],
        })
        for moment in state["key_moments"]  # 핵심 장면 수만큼 반복
    ]

# process_clip 노드 — 이 함수가 동시에 여러 번 실행됨
async def node_process_clip(state: PipelineState):
    clip = state["clip"]    # 각 인스턴스마다 다른 clip
    
    # 1. ffmpeg으로 9:16 클립 추출
    clip_path = await make_short(state["video_path"], clip.start, clip.end)
    
    # 2. ASS 자막 생성 + 번인
    final_path = await add_captions(clip_path, ...)
    
    # 3. 썸네일 생성
    thumb = await make_thumbnail(clip_path, ...)
    
    return {
        "results": [ShortResult(...)],  # operator.add로 자동 누적
    }
```

### operator.add — 병렬 결과 자동 합산

```python
# models.py / pipeline.py 내 State 정의

class PipelineState(TypedDict):
    # annotated=True + operator.add → 병렬 노드 결과가 자동으로 리스트에 추가됨
    results: Annotated[list[ShortResult], operator.add]
    #                                     ↑
    #         clip_0 결과: [ShortResult(0)]
    #         clip_1 결과: [ShortResult(1)]
    #         clip_2 결과: [ShortResult(2)]
    #         → 자동 합산: [ShortResult(0), ShortResult(1), ShortResult(2)]
```

**왜 중요한가?**
병렬 실행 중인 여러 노드가 동시에 같은 리스트에 결과를 추가하려 할 때,
`operator.add`가 **경합(race condition) 없이 안전하게 합산**을 보장합니다.

---

## 4. 핵심 개념 2 — SSE 실시간 스트리밍

### SSE(Server-Sent Events)란?

| 비교 | HTTP 폴링 | WebSocket | SSE |
|------|-----------|-----------|-----|
| 방향 | 클라→서버 반복 요청 | 양방향 | 서버→클라 단방향 |
| 연결 | 매번 새 연결 | 지속 연결 | 지속 연결 |
| 복잡도 | 낮음 | 높음 | 낮음 |
| 용도 | 일반 요청 | 채팅 | 진행률 스트리밍 |
| 이 프로젝트 | ❌ | ❌ | ✅ |

**쇼츠 생성은 서버→클라 단방향 푸시만 필요하므로 SSE가 최적입니다.**

### 서버 코드 (main.py)

```python
from sse_starlette.sse import EventSourceResponse

@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    async def generator():
        while True:
            job = jobs.get(job_id)         # 현재 작업 상태 조회
            if not job:
                yield {"data": json.dumps({"error": "not found"})}
                return

            # 현재 상태를 클라이언트에 전송
            yield {
                "data": json.dumps({
                    "status":   job.status,    # "running" | "done" | "error"
                    "step":     job.step,      # "전사 중..." | "핵심 장면 선정 중..." 등
                    "progress": job.progress,  # 0 ~ 100
                    "results":  [...],         # 완료 시 결과물 목록
                })
            }

            if job.status in ("done", "error"):
                return       # 완료 시 연결 종료

            await asyncio.sleep(0.5)   # 0.5초마다 상태 전송

    return EventSourceResponse(generator())
```

### 클라이언트 코드 (App.vue)

```javascript
// SSE 연결 시작
const es = new EventSource(`/api/jobs/${jobId}/events`)

es.onmessage = (event) => {
    const data = JSON.parse(event.data)
    
    progress.value = data.progress      // 프로그레스바 업데이트
    currentStep.value = data.step       // "전사 중..." 텍스트 업데이트
    
    if (data.status === "done") {
        results.value = data.results    // 결과물 표시
        es.close()                      // 연결 종료
    }
}

es.onerror = () => es.close()          // 에러 시 연결 종료
```

### 진행률 업데이트 흐름

```
파이프라인 노드 실행 중                     클라이언트
    │                                         │
    │ jobs[job_id].step = "오디오 추출 중"     │
    │ jobs[job_id].progress = 10              │
    │                                    ←────┤ 0.5초마다 GET /events
    │                                         │ → progress: 10, step: "오디오 추출 중"
    │ jobs[job_id].step = "음성 전사 중"      │
    │ jobs[job_id].progress = 25              │
    │                                    ←────┤ 0.5초마다 GET /events
    │                                         │ → progress: 25, step: "음성 전사 중"
    │                      ...               │
    │ jobs[job_id].status = "done"            │
    │ jobs[job_id].progress = 100             │
    │                                    ←────┤ GET /events
    │                                         │ → status: "done" → 연결 종료
```

---

## 5. 핵심 개념 3 — RAG (영상 질의응답)

### RAG(Retrieval-Augmented Generation)란?

```
일반 GPT:    "이 영상에서 주인공이 뭐라고 했나요?" → 모름 (훈련 데이터에 없음)

RAG 방식:
  1. [색인] 영상 전사 텍스트 → 청크로 분할 → 벡터 변환 → DB 저장
  2. [검색] 질문을 벡터화 → DB에서 가장 유사한 청크 검색
  3. [생성] 검색된 청크 + 질문 → GPT에게 "이 내용을 바탕으로 답하라"
```

### 이 프로젝트의 RAG 구현 (rag.py)

#### Step 1 — 색인 (영상 업로드 후 자동 실행)

```python
def index_segments(job_id: str, segments: list[dict]):
    """
    Whisper 전사 결과의 각 세그먼트를 ~30초 단위 청크로 묶어서 벡터 DB에 저장
    
    segments 예시:
    [
        {"start": 0.0,  "end": 5.2,  "text": "안녕하세요 오늘은"},
        {"start": 5.2,  "end": 12.4, "text": "파이썬 비동기에 대해"},
        ...
    ]
    """
    collection = chroma.get_or_create_collection(job_id)  # 영상별 독립 컬렉션
    
    chunks = []
    current_chunk = []
    current_duration = 0.0
    
    for seg in segments:
        current_chunk.append(seg)
        current_duration += seg["end"] - seg["start"]
        
        if current_duration >= 30.0:   # ~30초마다 청크 분리
            chunks.append(current_chunk)
            current_chunk = []
            current_duration = 0.0
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # 각 청크를 OpenAI 임베딩으로 벡터화
    texts = [" ".join(s["text"] for s in chunk) for chunk in chunks]
    embeddings = openai_client.embeddings.create(
        input=texts,
        model="text-embedding-3-small"   # 1536차원 벡터
    )
    
    # ChromaDB에 저장 (텍스트 + 벡터 + 타임스탬프 메타데이터)
    collection.add(
        ids=[f"chunk_{i}" for i in range(len(chunks))],
        documents=texts,
        embeddings=[e.embedding for e in embeddings.data],
        metadatas=[{
            "start": chunks[i][0]["start"],
            "end":   chunks[i][-1]["end"],
        } for i in range(len(chunks))]
    )
```

#### Step 2 & 3 — 질의 + 답변 생성

```python
def query(job_id: str, question: str) -> str:
    collection = chroma.get_collection(job_id)
    
    # 질문을 벡터화
    q_embedding = openai_client.embeddings.create(
        input=[question], model="text-embedding-3-small"
    ).data[0].embedding
    
    # 코사인 유사도로 가장 관련 있는 청크 3개 검색
    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=3,
        include=["documents", "metadatas"]
    )
    
    # 검색된 청크를 컨텍스트로 GPT에게 전달
    context_parts = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        start_min = int(meta["start"] // 60)
        start_sec = int(meta["start"] % 60)
        context_parts.append(f"[{start_min}분 {start_sec}초] {doc}")
    
    context = "\n\n".join(context_parts)
    
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"다음은 영상 전사 내용입니다:\n\n{context}\n\n이 내용을 바탕으로 답하세요."
            },
            {"role": "user", "content": question}
        ]
    )
    
    # 출처 타임스탬프 자동 추가
    return response.choices[0].message.content + "\n\n📍 " + ...
```

### RAG 시각화

```
질문: "이 영상에서 가장 중요한 내용이 뭔가요?"
    │
    ▼ text-embedding-3-small
[0.2, -0.8, 0.4, ...] (1536차원 벡터)
    │
    ▼ 코사인 유사도 계산
ChromaDB:
  chunk_0: "안녕하세요 오늘은..."    유사도: 0.31
  chunk_1: "핵심 포인트는..."        유사도: 0.89  ← 1위
  chunk_2: "마무리하면서..."          유사도: 0.72  ← 2위
  chunk_5: "첫 번째로..."            유사도: 0.68  ← 3위
    │
    ▼ 상위 3개 청크를 컨텍스트로
GPT-4o-mini: "제공된 내용에 따르면, 핵심 포인트는..."
    │
    ▼ 응답 + 타임스탬프
"제공된 영상의 핵심 내용은... 📍 2분 15초 참고"
```

---

## 6. 핵심 개념 4 — AI 창작 파이프라인

### 전체 흐름 (5단계)

```
사용자 입력                  서버 처리                    결과
─────────                  ────────                    ────
"MZ세대 재테크 꿀팁"  ──→  인터뷰 Q1: 타겟 시청자?
  "2030 직장인"       ──→  인터뷰 Q2: 톤/분위기?
  "친근하고 실용적"   ──→  인터뷰 Q3: 핵심 메시지?
  "월 50만원 저축법"  ──→  인터뷰 Q4: 목표 길이?
  "60초"             ──→  웹 검색 ("MZ 재테크 2024")
                          + 기획안 생성 (GPT-4o)    ──→  기획안 표시
  [승인]             ──→  스크립트 생성 (GPT-4o)    ──→  장면별 대본 표시
  [승인+편집]        ──→  영상 생성 시작
                          ├─ 장면1: TTS + 이미지 (동시)
                          ├─ 장면2: TTS + 이미지 (동시)
                          │   ...
                          └─ concat → 자막 번인       ──→  완성 영상 + 썸네일
```

### 인터뷰 단계 (ai_creator.py)

```python
INTERVIEW_QUESTIONS = [
    "이 영상의 주요 타겟 시청자는 누구인가요? (예: 20대 학생, 30대 직장인 등)",
    "원하는 영상의 톤과 분위기는 어떤가요? (예: 유머러스, 진지한, 친근한, 전문적)",
    "영상에서 전달하고 싶은 핵심 메시지나 행동 유도(CTA)는 무엇인가요?",
    "목표 영상 길이는 어느 정도인가요? (30초 / 60초 / 90초)",
]

async def interview_step(topic: str, step: int, answer: str | None, history: list) -> dict:
    if step < len(INTERVIEW_QUESTIONS):
        # 아직 질문이 남아있음 → 다음 질문 반환
        return {
            "type": "question",
            "question": INTERVIEW_QUESTIONS[step],
            "step": step,
        }
    else:
        # 모든 질문 완료 → 웹 검색 + 기획안 생성
        search_results = await web_search(topic)          # DuckDuckGo 검색
        outline = await generate_outline(topic, history, search_results)  # GPT-4o
        
        return {
            "type": "outline",
            "outline": outline,         # 기획안 내용
            "search_used": True,        # 웹 검색 사용 여부 표시
        }
```

### 기획안 생성 프롬프트 구조

```python
# ai_creator.py 내부

system_prompt = """
당신은 YouTube Shorts 전문 기획자입니다.
주어진 주제, 인터뷰 정보, 최신 웹 검색 결과를 바탕으로
바이럴 가능성이 높은 쇼츠 기획안을 JSON으로 작성하세요.
"""

user_prompt = f"""
주제: {topic}

인터뷰 내용:
- 타겟: {answers[0]}
- 톤: {answers[1]}
- 메시지: {answers[2]}
- 길이: {answers[3]}

최신 웹 검색 결과:
{formatted_search_results}

다음 JSON 형식으로 출력하세요:
{{
  "title_idea": "제목 아이디어",
  "hook": "첫 3초 훅 (시청자를 붙잡을 문장)",
  "key_points": ["포인트1", "포인트2", "포인트3"],
  "closing": "마무리 CTA",
  "tone_note": "특별 연출 지침"
}}
"""
```

### 스크립트 → 영상 변환 (create_pipeline.py)

```python
async def run_create_pipeline(job_id: str, script: ScriptData, out_dir: Path):
    scenes = script.scenes  # 예: 8개 장면 (60초 영상)
    
    # ① 모든 장면의 TTS + 이미지를 동시에 생성 (병렬!)
    #    → 장면 8개 × (TTS + 이미지) = 16개 작업이 동시 실행
    scene_results = await asyncio.gather(*[
        _process_scene(scene, out_dir)
        for scene in scenes
    ])
    
    # ② 각 장면을 (이미지 + 나레이션 음성)으로 영상 클립 생성
    clips = []
    for tts_path, img_path, duration in scene_results:
        clip = await _make_scene_clip(
            image_path=img_path,    # 배경 이미지
            audio_path=tts_path,    # 나레이션 음성
            duration=duration,      # TTS 길이에 맞게 클립 길이 결정
        )
        clips.append(clip)
    
    # ③ 모든 클립을 하나로 연결 (concat demuxer)
    raw_video = await concat_clips(clips)
    
    # ④ ASS 자막 번인
    final_video = await burn_subtitles(raw_video, scenes, [d for _,_,d in scene_results])
    
    # ⑤ 썸네일 = 첫 번째 장면 이미지 사용
    shutil.copy(scene_results[0][1], out_dir / "thumbnail.jpg")
```

```python
async def _process_scene(scene: SceneData, out_dir: Path):
    """장면 하나의 TTS와 이미지를 동시에 생성"""
    
    tts_path, img_path = await asyncio.gather(
        # 나레이션 텍스트 → 음성 파일 (.mp3)
        generate_tts(
            text=scene.narration,               # "MZ세대에게 딱 맞는 재테크 꿀팁"
            output_path=out_dir / f"tts_{scene.order}.mp3"
        ),
        # 이미지 프롬프트 → AI 이미지 (.jpg)
        generate_image(
            prompt=scene.image_prompt,          # "Young Korean professional..."
            output_path=out_dir / f"img_{scene.order}.jpg"
        ),
    )
    
    # TTS 음성 길이 측정 (ffprobe) → 클립 길이 결정에 사용
    duration = await get_audio_duration(tts_path)
    
    return tts_path, img_path, duration
```

---

## 7. 핵심 개념 5 — 비디오 처리 (ffmpeg)

### ffmpeg이란?
오픈소스 영상 처리 도구. 이 프로젝트에서 모든 영상 편집은 ffmpeg 명령어를 Python `subprocess`로 실행합니다.

### 주요 ffmpeg 작업 (shorts_maker.py)

#### 오디오 추출 (transcriber.py)
```python
# MP4에서 MP3 추출 (Whisper에 전달하기 위해)
subprocess.run([
    "ffmpeg", "-i", str(video_path),   # 입력: 원본 영상
    "-ar", "16000",                     # 샘플레이트 16kHz (Whisper 권장)
    "-ac", "1",                         # 모노 채널
    "-c:a", "libmp3lame",              # MP3 코덱
    str(audio_path)                     # 출력: audio.mp3
])
```

#### 9:16 클립 추출 (shorts_maker.py)
```python
# 핵심 장면 구간 추출 + 세로 포맷(9:16) 변환
subprocess.run([
    "ffmpeg",
    "-ss", str(start),          # 시작 시간 (초)
    "-to", str(end),            # 종료 시간 (초)
    "-i", str(video_path),      # 입력 영상
    "-vf",
    "crop=ih*9/16:ih,"          # 가로를 9:16 비율로 크롭
    "scale=1080:1920,"          # 1080x1920 (쇼츠 표준)
    "fade=in:0:15,"             # 처음 15프레임 페이드 인
    f"fade=out:{end-start-0.5}:15",  # 마지막 15프레임 페이드 아웃
    "-c:v", "libx264",          # H.264 비디오 코덱
    "-crf", "23",               # 품질 (낮을수록 고품질, 23=중간)
    "-c:a", "aac",              # AAC 오디오 코덱
    str(output_path)
])
```

#### AI 창작 모드 — 이미지를 영상으로 변환
```python
# 정지 이미지 + 나레이션 오디오 → 영상 클립
subprocess.run([
    "ffmpeg",
    "-loop", "1",               # 이미지를 반복 (정지 상태)
    "-i", str(image_path),      # 배경 이미지
    "-i", str(audio_path),      # 나레이션 음성
    "-c:v", "libx264",
    "-t", str(duration),        # TTS 길이만큼만 클립 생성
    "-pix_fmt", "yuv420p",      # 호환성 픽셀 포맷
    "-vf", "scale=1080:1920",   # 9:16 비율
    str(output_path)
])
```

#### 자막 번인 (caption_maker.py)
```python
# ASS 자막 파일을 영상 픽셀에 직접 렌더링
subprocess.run([
    "ffmpeg",
    "-i", str(video_path),          # 원본 클립
    "-vf", f"ass={str(ass_path)}",  # libass 필터로 자막 렌더링
    "-c:v", "libx264",
    str(output_path)
])
```

### ASS 자막 형식 (caption_maker.py)

```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, ...
Style: Default,Malgun Gothic,82,...
#                              ↑ 82px 폰트 — 모바일에서 잘 보이는 크기

[Events]
Format: Start, End, Style, Text
Dialogue: 0:00:01.00,0:00:03.50,Default,안녕하세요 오늘은
Dialogue: 0:00:03.50,0:00:06.20,Default,파이썬 비동기에 대해 알아볼게요
```

---

## 8. 핵심 개념 6 — TTS (음성 합성)

### 두 가지 TTS (tts_maker.py)

```python
VOICE_PRIMARY  = "ko-KR-SunHiNeural"   # Microsoft Azure Neural TTS
VOICE_FALLBACK = "onyx"                  # OpenAI TTS-1-HD

async def generate_tts(text: str, output_path: Path) -> Path:
    try:
        # 1순위: edge-tts (Microsoft) — API 키 불필요, 무료
        communicate = edge_tts.Communicate(
            text=text,
            voice=VOICE_PRIMARY,
            rate="+10%"     # 약간 빠르게 (쇼츠에 적합)
        )
        await communicate.save(str(output_path))
        
    except Exception:
        # 폴백: OpenAI TTS (유료이지만 안정적)
        response = openai_client.audio.speech.create(
            model="tts-1-hd",
            voice=VOICE_FALLBACK,
            input=text,
        )
        response.stream_to_file(output_path)
    
    return output_path
```

### edge-tts란?

- Microsoft Azure의 Neural TTS 서비스를 **비공식으로 무료 사용**하는 Python 라이브러리
- 브라우저의 Microsoft Edge가 웹 페이지 읽기에 사용하는 TTS 엔진과 동일
- `ko-KR-SunHiNeural`은 한국어 중 가장 자연스러운 여성 음성
- API 키 없이 사용 가능 → **운영 비용 0원**

### TTS 길이 측정 (AI 창작 모드에서 중요)

```python
async def get_audio_duration(audio_path: Path) -> float:
    """
    AI 창작 모드에서 각 장면의 클립 길이 = TTS 음성 길이
    → TTS 생성 후 정확한 길이를 알아야 영상 타임라인이 맞음
    """
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(audio_path)
        ],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())  # 예: 4.82 (초)
```

---

## 9. 핵심 개념 7 — AI 이미지 생성

### Gemini를 사용한 핵심 장면 선정 (key_moments.py)

```python
# 폴백 체인 — 순서대로 시도, 실패하면 다음 모델로
GEMINI_MODELS = [
    "gemini-2.5-flash",      # 최신, 가장 좋음
    "gemini-2.0-flash",      # 차선
    "gemini-flash-latest",   # 항상 존재하는 alias
]

async def select_key_moments(
    transcription_segments: list[dict],
    n_clips: int = 3,
) -> list[KeyMoment]:
    
    # 타임스탬프 포함 전사 텍스트 구성
    formatted = "\n".join(
        f"[{s['start']:.1f}s - {s['end']:.1f}s]: {s['text']}"
        for s in transcription_segments
    )
    
    prompt = f"""
다음은 영상 전사 텍스트입니다:
{formatted}

YouTube Shorts에 최적화된 핵심 장면 {n_clips}개를 선정하세요.
각 장면은 30~90초 길이로 선정하고, 다음 기준을 적용하세요:
- 드라마틱한 전환점 또는 핵심 인사이트
- 시청자 반응을 유도하는 유머, 감동, 놀라움
- 독립적으로 이해 가능한 완결된 내용

반드시 다음 JSON 형식으로만 응답:
{{
  "clips": [
    {{"start": 10.5, "end": 45.2, "reason": "선정 이유"}}
  ]
}}
"""
    
    for model_name in GEMINI_MODELS:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
                config={"response_mime_type": "application/json"},  # JSON 강제
            )
            data = json.loads(response.text)
            return [KeyMoment(**clip) for clip in data["clips"]]
            
        except Exception as e:
            if "429" in str(e) or "503" in str(e):   # 할당량 초과 or 과부하
                await asyncio.sleep(10)               # 10초 대기 후 재시도
                continue
    
    raise RuntimeError("모든 Gemini 모델 실패")
```

### OpenAI gpt-image-1 썸네일 (thumbnail_gen.py)

```python
async def generate_ai_thumbnail(image_prompt: str, output_path: Path) -> Path:
    try:
        response = openai_client.images.generate(
            model="gpt-image-1",
            prompt=f"""
YouTube Shorts thumbnail for: {image_prompt}

Requirements:
- 9:16 vertical format (portrait)
- Bold, eye-catching design
- Korean YouTube style (bright colors, large text space)
- No text in image (text will be added separately)
- Cinematic quality, professional lighting
""",
            size="1024x1536",    # 9:16 세로 포맷
            quality="medium",    # low/medium/high (high는 비용 높음)
        )
        
        # base64 이미지 데이터를 파일로 저장
        image_data = base64.b64decode(response.data[0].b64_json)
        output_path.write_bytes(image_data)
        
    except Exception:
        # AI 실패 시 폴백: 클립의 1/3 지점에서 프레임 추출
        await extract_frame(clip_path, output_path, position=0.33)
    
    return output_path
```

---

## 10. 프론트엔드 아키텍처

### Vue 3 Composition API 패턴

```javascript
// App.vue 핵심 구조
import { ref, computed, onMounted } from 'vue'

// 상태 (ref = 반응형 변수)
const activeTab = ref('upload')      // 현재 탭
const jobId = ref(null)              // 현재 작업 ID
const progress = ref(0)              // 진행률 (0~100)
const currentStep = ref('')          // 현재 단계 설명
const results = ref([])              // 완료된 쇼츠 목록
const isProcessing = ref(false)      // 처리 중 여부

// 영상 업로드 함수
async function uploadVideo(file) {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData
    })
    const data = await response.json()
    jobId.value = data.job_id          // 작업 ID 저장
    
    startSSE(data.job_id)              // SSE 연결 시작
}

// SSE 실시간 진행률 수신
function startSSE(id) {
    const es = new EventSource(`/api/jobs/${id}/events`)
    
    es.onmessage = (event) => {
        const data = JSON.parse(event.data)
        progress.value = data.progress
        currentStep.value = data.step
        
        if (data.status === 'done') {
            results.value = data.results
            isProcessing.value = false
            es.close()
        }
    }
}
```

### AI 창작 탭의 단계별 상태 관리 (AICreateTab.vue)

```javascript
// 5가지 phase 상태
const phase = ref('interview')   // interview → outline → preview → generating → done

// phase 전환 흐름
async function handleInterviewSubmit(answer) {
    const res = await fetch('/api/create/interview', {
        method: 'POST',
        body: JSON.stringify({ topic, step: interviewStep.value, answer, history })
    })
    const data = await res.json()
    
    if (data.type === 'question') {
        // 아직 질문 남음 → 다음 질문 표시
        currentQuestion.value = data.question
        interviewStep.value++
    } else if (data.type === 'outline') {
        // 인터뷰 완료 → 기획안 화면으로 전환
        outline.value = data.outline
        phase.value = 'outline'           // ← 화면 전환!
    }
}

async function approveOutline() {
    const res = await fetch('/api/create/script', { ... })
    script.value = await res.json()
    phase.value = 'preview'              // ← 대본 미리보기로 전환
}

async function startGeneration() {
    const res = await fetch('/api/create/generate', { ... })
    const { job_id } = await res.json()
    phase.value = 'generating'           // ← 생성 중으로 전환
    startCreateSSE(job_id)
}
```

### 결과 그리드 (ResultsGrid.vue)

```html
<!-- 각 쇼츠 카드 구조 -->
<div v-for="short in results" class="short-card">
    <!-- 썸네일 / 영상 플레이어 토글 -->
    <div @click="togglePlay(short)">
        <img v-if="!short.playing" :src="short.thumbnail_url" />
        <video v-else :src="short.video_url" autoplay controls />
    </div>
    
    <!-- 선정 이유 -->
    <p>{{ short.reason }}</p>
    
    <!-- 영상 내 위치 타임라인 -->
    <div class="timeline">
        <div class="marker" :style="{ left: (short.start / totalDuration * 100) + '%' }" />
    </div>
    
    <!-- 썸네일 전환 버튼 -->
    <button @click="toggleThumbnail(short)">
        {{ short.showAI ? 'AI 썸네일' : '원본 프레임' }}
    </button>
    
    <!-- 다운로드 -->
    <a :href="short.video_url" download>영상 다운로드</a>
    <a :href="short.thumbnail_url" download>썸네일 다운로드</a>
</div>
```

---

## 11. 백엔드 API 전체 목록

### 영상 분석 API (main.py)

| 메서드 | 경로 | 설명 |
|-------|------|------|
| `POST` | `/api/upload` | 영상 파일 업로드 (최대 500MB) → job_id 반환 |
| `POST` | `/api/youtube` | YouTube URL → yt-dlp 다운로드 후 파이프라인 실행 → job_id 반환 |
| `GET` | `/api/jobs/{job_id}` | 작업 상태 조회 |
| `GET` | `/api/jobs/{job_id}/events` | SSE 실시간 스트리밍 |
| `POST` | `/api/jobs/{job_id}/chat` | RAG 질의응답 |
| `GET` | `/api/history` | 완료된 모든 작업 목록 |
| `DELETE` | `/api/history/{job_id}` | 작업 삭제 |
| `GET` | `/outputs/{path}` | 생성된 파일 서빙 (정적) |

### AI 창작 API (routers/create.py)

| 메서드 | 경로 | 설명 |
|-------|------|------|
| `POST` | `/api/create/interview` | 인터뷰 단계 진행 |
| `POST` | `/api/create/script` | 기획안 → 스크립트 생성 |
| `POST` | `/api/create/generate` | 스크립트 → 영상 생성 시작 |
| `GET` | `/api/create/jobs/{job_id}/events` | SSE 실시간 스트리밍 |
| `GET` | `/api/create/jobs/{job_id}` | 창작 작업 상태 조회 |

### 요청/응답 예시

```json
// POST /api/upload 응답
{
    "job_id": "a3f7b2c1-...",
    "status": "started"
}

// GET /api/jobs/{id}/events 스트림
data: {"status": "running", "step": "음성 전사 중...", "progress": 25}
data: {"status": "running", "step": "핵심 장면 선정 중...", "progress": 40}
data: {"status": "running", "step": "쇼츠 클립 생성 중 (2/3)...", "progress": 70}
data: {"status": "done", "progress": 100, "results": [...]}

// POST /api/create/interview 응답 (질문 단계)
{
    "type": "question",
    "question": "원하는 영상의 톤과 분위기는 어떤가요?",
    "step": 1
}

// POST /api/create/interview 응답 (완료 단계)
{
    "type": "outline",
    "outline": {
        "title_idea": "MZ세대 필수 재테크 꿀팁 3가지",
        "hook": "월급의 10%만 써도 1년에 600만원?",
        "key_points": ["자동이체 설정법", "파킹통장 활용", "소액 ETF 투자"],
        "closing": "지금 바로 은행 앱 열어보세요!",
        "tone_note": "친근하되 신뢰감 있는 톤"
    },
    "search_used": true
}
```

---

## 12. 데이터 모델 (models.py)

```python
# 영상 분석 작업 상태
class Job(BaseModel):
    job_id: str
    status: str          # "running" | "done" | "error"
    step: str            # 현재 처리 단계 설명
    progress: int        # 0~100
    video_path: str
    results: list[ShortResult]
    highlight_reel: str | None
    created_at: datetime
    error: str | None

# 생성된 쇼츠 하나의 정보
class ShortResult(BaseModel):
    clip_id: str
    video_url: str           # /outputs/{job_id}/clip_0.mp4
    thumbnail_url: str       # /outputs/{job_id}/thumb_0.jpg
    ai_thumbnail_url: str | None   # AI 생성 썸네일 (선택)
    start: float             # 원본 영상 내 시작 시간 (초)
    end: float               # 원본 영상 내 종료 시간 (초)
    reason: str              # Gemini가 선정한 이유

# 핵심 장면 정보 (Gemini 출력)
class KeyMoment(BaseModel):
    start: float
    end: float
    reason: str

# AI 창작 — 장면 하나
class SceneData(BaseModel):
    order: int
    narration: str       # 한국어 나레이션 텍스트
    image_prompt: str    # 영어 이미지 생성 프롬프트

# AI 창작 — 전체 스크립트
class ScriptData(BaseModel):
    title: str
    target_duration: int     # 30 | 60 | 90 (초)
    scenes: list[SceneData]  # 장면 목록
```

---

## 13. 코드 상세 분석 (파일별)

### main.py — FastAPI 앱 설정

```python
from fastapi import FastAPI, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Shorts Maker API")

# CORS 설정 — 프론트엔드(포트 5173)에서 백엔드(포트 8000)로 요청 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # 개발 중: 전체 허용 (프로덕션에서는 특정 도메인으로 제한)
    allow_methods=["*"],
    allow_headers=["*"],
)

# 생성된 파일을 URL로 서빙
app.mount("/outputs",        StaticFiles(directory="outputs"),        name="outputs")
app.mount("/create_outputs", StaticFiles(directory="create_outputs"), name="create_outputs")

# 라우터 등록
app.include_router(create_router, prefix="")   # AI 창작 API

# 작업 상태 인메모리 저장 (재시작 시 초기화됨)
jobs: dict[str, Job] = {}
create_jobs: dict[str, CreateJob] = {}

@app.post("/api/upload")
async def upload_video(
    file: UploadFile,
    background_tasks: BackgroundTasks,  # 비동기 백그라운드 실행
):
    job_id = str(uuid.uuid4())          # 고유 작업 ID 생성
    
    # 업로드된 파일 저장
    video_path = Path("outputs") / job_id / "original.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(video_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # 작업 상태 초기화
    jobs[job_id] = Job(job_id=job_id, status="running", progress=0, ...)
    
    # 파이프라인을 백그라운드에서 실행 (요청은 즉시 반환)
    background_tasks.add_task(run_pipeline, job_id, video_path, jobs)
    
    return {"job_id": job_id, "status": "started"}
```

### pipeline.py — LangGraph 파이프라인 빌드

```python
def build_pipeline() -> CompiledGraph:
    """LangGraph 파이프라인 그래프 구성"""
    
    g = StateGraph(PipelineState)
    
    # 노드 등록 (각 노드는 async 함수)
    g.add_node("check_duration",  node_check_duration)
    g.add_node("extract_audio",   node_extract_audio)
    g.add_node("transcribe",      node_transcribe)
    g.add_node("index_rag",       node_index_rag)
    g.add_node("select_moments",  node_select_moments)
    g.add_node("process_clip",    node_process_clip)
    g.add_node("make_highlight",  node_make_highlight)
    g.add_node("save_meta",       node_save_meta)
    
    # 직선 엣지 (순차 실행)
    g.add_edge(START,             "check_duration")
    g.add_edge("check_duration",  "extract_audio")
    g.add_edge("extract_audio",   "transcribe")
    g.add_edge("transcribe",      "index_rag")
    g.add_edge("index_rag",       "select_moments")
    
    # 조건부 엣지 (팬아웃 — 핵심 장면 수만큼 병렬 분기)
    g.add_conditional_edges(
        "select_moments",
        dispatch_clips,           # Send() 리스트 반환 함수
    )
    
    # 병렬 클립 처리 완료 후 합류
    g.add_edge("process_clip",    "make_highlight")
    g.add_edge("make_highlight",  "save_meta")
    g.add_edge("save_meta",       END)
    
    return g.compile()

pipeline = build_pipeline()   # 모듈 로드 시 한 번만 컴파일
```

---

## 14. 예상 질문 & 모범 답변

### Q1. "LangGraph를 왜 사용했나요? 그냥 함수 호출하면 안 되나요?"

**A:**
> 핵심은 **병렬 팬아웃**입니다. 핵심 장면이 3개면 3개의 클립 처리 작업이 동시에 실행되어야 합니다.
> 일반 for 루프로는 순차 실행이 되고, asyncio.gather()로는 가능하지만 상태 관리가 복잡해집니다.
> LangGraph의 `Send()` API는 "장면 수만큼 동일 노드를 병렬 실행하고, 각 결과를 자동으로 State에 누적"하는 기능을 
> 선언적으로 표현할 수 있어서 선택했습니다.
> 또한 나중에 human-in-the-loop(사람이 중간에 개입)나 체크포인트 재개 기능을 추가하기도 쉽습니다.

### Q2. "SSE와 WebSocket의 차이가 뭔가요? 왜 SSE를 선택했나요?"

**A:**
> WebSocket은 **양방향** 통신이고, SSE는 **서버→클라이언트 단방향** 입니다.
> 진행률 스트리밍은 서버가 클라이언트에게 상태를 밀어주는 단방향이므로 WebSocket의 복잡도가 불필요합니다.
> SSE는 일반 HTTP 위에서 동작해서 프록시/방화벽 문제가 없고, 
> 브라우저 기본 `EventSource` API로 재연결도 자동 처리됩니다.
> 구현도 더 간단합니다 — FastAPI의 `EventSourceResponse` 한 줄로 충분합니다.

### Q3. "RAG에서 ChromaDB를 선택한 이유가 뭔가요?"

**A:**
> 이 프로젝트는 로컬에서 실행되는 앱이라 외부 서비스 의존을 최소화하고 싶었습니다.
> ChromaDB는 **로컬 파일로 영구 저장**되어 서버 재시작 후에도 색인이 유지되고,
> 추가 서버 없이 Python 패키지 하나로 완성됩니다.
> Pinecone이나 Weaviate 같은 클라우드 벡터 DB는 API 키와 월 비용이 필요하지만
> ChromaDB는 완전 무료입니다.

### Q4. "edge-tts는 공식 API가 아닌데 안정성이 걱정되지 않나요?"

**A:**
> 맞습니다, 그래서 **폴백 체인**을 구현했습니다.
> edge-tts가 실패하면 자동으로 OpenAI의 `tts-1-hd`로 전환됩니다.
> edge-tts는 API 키 없이 무료라 개발/테스트에 비용 부담이 없고,
> 실제로 Microsoft Azure 인프라를 사용하기 때문에 안정성도 상당히 높습니다.

### Q5. "Gemini 모델 폴백 체인은 어떻게 동작하나요?"

**A:**
> `gemini-2.5-flash` → `gemini-2.0-flash` → `gemini-flash-latest` 순서로 시도합니다.
> 429 (할당량 초과) 또는 503 (서비스 불안정) 에러가 발생하면 10초 대기 후 다음 모델을 시도합니다.
> 이렇게 하면 특정 모델 할당량이 소진되거나 일시적 장애가 있어도 서비스가 계속 동작합니다.

### Q6. "영상 처리에 왜 Python 라이브러리 대신 ffmpeg을 사용했나요?"

**A:**
> `moviepy` 같은 Python 라이브러리도 있지만, 내부적으로 ffmpeg을 래핑하기 때문에 
> 오히려 성능이 떨어지고 의존성 문제가 생길 수 있습니다.
> ffmpeg을 직접 `subprocess`로 호출하면 최신 코덱 지원, 세밀한 파라미터 제어, 
> ASS 자막 번인(libass) 등 고급 기능을 그대로 사용할 수 있습니다.
> 비디오 처리는 CPU 집약적 작업이라 `asyncio.to_thread()`로 별도 스레드에서 실행해 이벤트 루프를 블로킹하지 않습니다.

### Q7. "인메모리 jobs dict는 서버 재시작 시 데이터가 날아가는 문제가 있지 않나요?"

**A:**
> 맞습니다. 현재는 개발/데모용 설계입니다.
> 프로덕션이라면 Redis나 SQLite를 사용해 영속성을 확보해야 합니다.
> 단, 완료된 결과물은 파일 시스템(`outputs/`)과 `meta.json`으로 저장되기 때문에
> 서버 재시작 후에도 `/api/history` API가 파일 시스템을 스캔해서 기존 결과를 복원합니다.

### Q8. "동시에 여러 사용자가 업로드하면 어떻게 되나요?"

**A:**
> `BackgroundTasks`로 각 업로드가 독립적인 비동기 태스크로 실행되고,
> 모든 작업은 고유 `job_id`(UUID)로 격리됩니다.
> 현재는 단일 서버이므로 CPU 집약적 ffmpeg 작업이 동시에 많이 실행되면 
> 성능 저하가 있을 수 있습니다.
> 스케일아웃이 필요하다면 Celery + Redis 같은 태스크 큐로 전환이 필요합니다.

---

## 15. 기술 선택 이유 (Why not X?)

| 기술 | 선택 이유 | 대안과 비교 |
|------|----------|-----------|
| **FastAPI** | 비동기 기본 지원, SSE 내장, 자동 API 문서 | Flask: 동기 기반이라 비동기 번거로움 |
| **LangGraph** | 상태 머신 기반 팬아웃 병렬화, human-in-the-loop 확장성 | LangChain: 단순 체인은 되지만 복잡한 병렬 분기 불편 |
| **Google Gemini** | 긴 컨텍스트 (전사 텍스트 전체 입력 가능), 상대적으로 저렴 | GPT-4o: 더 비쌈, Claude: 이미지 생성 미지원 |
| **OpenAI Whisper** | 한국어 전사 품질 최상, 세그먼트 타임스탬프 제공 | Google STT: API 설정 복잡, Clova: 국내 전용 |
| **ChromaDB** | 로컬 파일 저장, 무료, Python 패키지만으로 완결 | Pinecone: 클라우드 유료, Weaviate: 서버 별도 필요 |
| **edge-tts** | API 키 없음, Microsoft Azure 품질, 무료 | Google TTS: 유료, Clova: 국내 전용, OpenAI TTS: 유료 |
| **Vue 3** | Composition API로 복잡한 상태 관리 가능, 경량 | React: 더 무겁고 설정 복잡, Svelte: 생태계 작음 |
| **SSE** | HTTP 기반 단순 구현, 재연결 자동, 브라우저 기본 지원 | WebSocket: 양방향 불필요한데 오버엔지니어링 |
| **ffmpeg** | 모든 포맷 지원, ASS 자막 번인, 최고 성능 | moviepy: ffmpeg 래퍼라 오버헤드, OpenCV: 비디오 편집 불편 |

---

## 16. 시스템 한계 & 개선 방향

### 현재 한계

| 한계 | 영향 | 개선 방향 |
|------|------|----------|
| 인메모리 job 저장 | 서버 재시작 시 진행 중 작업 손실 | Redis 또는 SQLite로 영속화 |
| 단일 서버 구조 | 동시 사용자 증가 시 성능 저하 | Celery + Redis 태스크 큐 |
| ffmpeg 로컬 설치 필요 | 배포 환경 의존성 관리 | Docker 컨테이너화 |
| OpenAI 비용 | gpt-image-1, Whisper 사용료 | 오픈소스 대안 (Stable Diffusion, Faster-Whisper) |
| 한국어 특화 부재 | 다국어 확장 어려움 | 언어 감지 후 자동 TTS 음성 선택 |
| 재시도 로직 없음 | 클립 생성 중 네트워크 오류 시 전체 재시작 | 노드별 체크포인트 (LangGraph checkpointer) |

### 확장 가능한 기능

1. ✅ **유튜브 직접 링크 입력** — `yt-dlp`로 영상 다운로드 후 파이프라인 실행 (구현 완료: `POST /api/youtube`, UploadZone YouTube 탭)
2. **자동 업로드** — YouTube Data API로 생성된 쇼츠 자동 게시
3. **A/B 썸네일 테스트** — 여러 썸네일 생성 후 CTR 비교
4. **스타일 커스텀** — 자막 폰트/색상, 페이드 효과 선택 UI
5. **배치 처리** — 여러 영상 동시 업로드 → 큐 관리

---

## 빠른 복습 체크리스트

아래 질문에 30초 내로 답할 수 있으면 완전히 이해한 것입니다.

- [ ] LangGraph에서 `Send()`가 하는 일을 한 문장으로 설명할 수 있다
- [ ] SSE와 WebSocket의 차이점과 이 프로젝트에서 SSE를 선택한 이유를 말할 수 있다
- [ ] RAG의 3단계 (색인 → 검색 → 생성)를 설명할 수 있다
- [ ] AI 창작 모드의 5단계 플로우를 순서대로 말할 수 있다
- [ ] `operator.add`가 병렬 실행에서 왜 필요한지 설명할 수 있다
- [ ] edge-tts가 실패했을 때 어떻게 되는지 말할 수 있다
- [ ] ffmpeg으로 9:16 변환이 어떻게 되는지 설명할 수 있다
- [ ] ChromaDB를 선택한 이유를 다른 옵션과 비교해서 말할 수 있다
- [ ] `BackgroundTasks`의 역할을 설명할 수 있다
- [ ] 진행률 업데이트가 어떤 경로로 클라이언트에 전달되는지 말할 수 있다
