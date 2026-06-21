# Pipeline / Node Pattern — Shorts Maker

추출 시각: 2026-06-17
샘플 파일 수: 2 (backend/pipeline.py, backend/create_pipeline.py)
신뢰도: HIGH (전 노드/파이프라인 통독)

---

## 권장 패턴

### LangGraph 노드 시그니처 + 반환 규약
빈도: 100% (8/8 LangGraph 노드)

```python
# 일반 노드: state 전체를 받아 dict 반환
async def node_get_duration(state: PipelineState) -> dict:
    jobs, job_id = state["jobs"], state["job_id"]
    _update(jobs, job_id, status=JobStatus.PROCESSING, step="영상 길이 확인 중...", progress=5)

    duration = await get_video_duration(Path(state["video_path"]))
    if duration <= 0:
        raise ValueError("영상 길이를 읽을 수 없습니다.")
    _update(jobs, job_id, video_duration=round(duration, 1))
    return {"duration": duration}   # ← 변경된 State 채널 키만 반환

# fan-out 수신 노드: payload dict를 받아 dict 반환
async def node_process_clip(payload: dict) -> dict:
    moment: KeyMoment = payload["moment"]
    job_id: str = payload["job_id"]
    # ...
    return {"results": [ShortResult(...)]}   # ← Annotated[list, operator.add] 채널
```

규칙:
- 노드 이름 접두어: `node_` 필수
- 일반 노드: `async def node_xxx(state: PipelineState) -> dict`
- fan-out 수신 노드(Send target): `async def node_xxx(payload: dict) -> dict`
- 반환값은 State 채널 키만 포함하는 dict (변경 없는 채널은 생략)
- `return {}` 도 허용 (node_finalize — side-effect만 있는 경우)

---

### PipelineState TypedDict 채널 선언
빈도: 단일 파일 (pipeline.py)

```python
class PipelineState(TypedDict):
    # ── 입력 파라미터 (run_pipeline에서 주입) ──
    job_id: str
    video_path: str
    output_dir: str
    use_ai_thumbnail: bool
    jobs: Any               # dict[str, Job] — mutable reference, 노드 간 진행률 공유

    # ── 파이프라인 채널 (노드 간 전달) ──
    duration: float
    has_knowledge: bool
    audio_path: str
    segments: list
    full_text: str
    moments: list
    results: Annotated[list, operator.add]   # fan-out 병렬 결과 누적
    highlight_reel_url: Optional[str]
```

핵심: `Annotated[list, operator.add]`는 Send fan-out 결과를 race condition 없이 누적하는 패턴.

---

### Send fan-out 패턴 (node_dispatch_clips)
빈도: 1/1 사용 사례 (dispatch → process 패턴)

```python
def node_dispatch_clips(state: PipelineState):
    """Fan-out: 각 핵심 장면을 node_process_clip으로 병렬 분기."""
    _update(state["jobs"], state["job_id"],
            step=f"쇼츠 {len(state['moments'])}개 생성 중...", progress=55)
    return [
        Send("node_process_clip", {          # ← Send(노드이름, payload_dict)
            "moment": m,
            "job_id": state["job_id"],
            "video_path": state["video_path"],
            "output_dir": state["output_dir"],
            "segments": state["segments"],
            "use_ai_thumbnail": state["use_ai_thumbnail"],
        })
        for m in state["moments"]
    ]

# 그래프 빌더에서 등록
g.add_conditional_edges("node_select_moments", node_dispatch_clips, ["node_process_clip"])
g.add_edge("node_process_clip", "node_concat_highlight")
```

규칙:
- dispatch 노드는 `async def` 아님 (sync도 허용)
- Send payload에 jobs mutable reference를 포함하면 fan-out 노드에서 진행률 갱신 가능 (이 프로젝트에서는 포함하지 않음 — node_process_clip은 jobs 접근 불필요)
- fan-out 수신 노드 결과는 반드시 `Annotated[list, operator.add]` 채널에 리스트로 반환

---

### StateGraph 빌더 등록 순서
빈도: 단일 (pipeline.py)

```python
def _build_graph() -> StateGraph:
    g = StateGraph(PipelineState)

    # 1. 모든 노드 등록
    g.add_node("node_get_duration", node_get_duration)
    g.add_node("node_extract_audio", node_extract_audio)
    # ... (나머지 노드들)

    # 2. 직선 엣지
    g.add_edge(START, "node_get_duration")
    g.add_edge("node_get_duration", "node_extract_audio")
    # ...

    # 3. 조건 엣지 (fan-out)
    g.add_conditional_edges("node_select_moments", node_dispatch_clips, ["node_process_clip"])
    g.add_edge("node_process_clip", "node_concat_highlight")
    g.add_edge("node_finalize", END)

    return g.compile()

_graph = _build_graph()   # ← 모듈 로드 시 1회 컴파일, 재사용
```

---

### 진행률 갱신 헬퍼 `_update`
빈도: 100% (모든 노드에서 사용 — pipeline.py, create_pipeline.py 각 정의)

```python
def _update(jobs: dict, job_id: str, **kwargs):
    job = jobs[job_id]
    for k, v in kwargs.items():
        setattr(job, k, v)

# 사용 예
_update(jobs, job_id, status=JobStatus.PROCESSING, step="오디오 추출 중...", progress=10)
_update(jobs, job_id, step="완료!", status=JobStatus.DONE, progress=100)
```

주의: pipeline.py와 create_pipeline.py에 동일 함수가 각각 정의됨 (중복). 공통 util 모듈로 추출 권장.

---

### run_pipeline 진입점 시그니처
빈도: 단일

```python
async def run_pipeline(
    job_id: str,
    video_path: Path,
    output_dir: Path,
    jobs: dict,
    use_ai_thumbnail: bool = True,
):
    try:
        await _graph.ainvoke({
            "job_id": job_id,
            "video_path": str(video_path),   # ← Path → str 변환 (State는 str 타입)
            "output_dir": str(output_dir),
            "use_ai_thumbnail": use_ai_thumbnail,
            "jobs": jobs,
            # 나머지 채널 초기값 명시
            "duration": 0.0,
            "audio_path": "",
            "segments": [],
            "full_text": "",
            "moments": [],
            "results": [],
            "highlight_reel_url": None,
            "has_knowledge": False,
        })
    except Exception as e:
        job = jobs.get(job_id)
        if job:
            setattr(job, "status", JobStatus.ERROR)
            setattr(job, "step", "오류 발생")
            setattr(job, "error", f"{type(e).__name__}: {e}" if str(e) else type(e).__name__)
```

---

### asyncio 파이프라인 (create_pipeline.py) 패턴
빈도: 단일

```python
async def run_create_pipeline(job_id, script, output_dir, create_jobs):
    job_out = output_dir / job_id
    job_out.mkdir(parents=True, exist_ok=True)

    try:
        # 단계별 진행률 갱신 + asyncio.gather 병렬
        _update(create_jobs, job_id, status=JobStatus.PROCESSING, step="① ...", progress=10)
        scene_results = await asyncio.gather(
            *[_process_scene(scene, job_out) for scene in scenes]
        )                                               # ← fail-fast 주의

        # 순차 처리 (각 클립 생성)
        for i, (tts_path, img_path, _) in enumerate(scene_results):
            await _make_scene_clip(img_path, tts_path, clip_path)

    except Exception as e:
        _update(create_jobs, job_id,
                status=JobStatus.ERROR, step="오류 발생",
                error=f"{type(e).__name__}: {e}" if str(e) else type(e).__name__)
```

단계 번호 표기: `"① TTS + 이미지 생성 중..."`, `"② 장면별 영상 클립 합성 중..."` (순서 파악용)

---

### meta.json 저장 (_save_meta)
빈도: 100% (완료 시 항상 호출 — 두 파이프라인 공통)

```python
def _save_meta(job_out: Path, job: Job):
    meta = job.model_dump()
    with open(job_out / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

# node_finalize / run_create_pipeline 완료 블록 마지막에 호출
_save_meta(job_out, jobs[job_id])
```

---

## 안티패턴 (피해야 할 패턴)

### 노드별 try/except 부재
- 현황: run_pipeline의 최상위 단일 try/except만 존재. 각 노드에는 에러 핸들링 없음.
- 위치: pipeline.py 전체 노드
- 위험: 어느 노드에서 실패했는지 Job.step/error 메시지에 미반영
- 권고: 노드별 에러를 잡아 step에 "N번 노드 실패: XXX" 기록 후 재 raise

### asyncio.gather fail-fast
- 위치: create_pipeline.py:124 `await asyncio.gather(*[_process_scene(...) for scene in scenes])`
- 위험: 한 장면 TTS/이미지 생성 실패 시 나머지 장면 결과도 버려짐 + 고아 태스크 가능
- 권고: `asyncio.gather(..., return_exceptions=True)` + 부분 실패 처리

### State 채널 미선언 사용
- 현황: `thumbnail_prompts`, `thumbnail_sketches` 는 State에 선언되지 않음
- 권고: 신규 노드가 반환하는 모든 키는 PipelineState에 사전 선언

### `jobs` mutable reference를 State에 포함
- 현황: `jobs: Any` 가 State에 포함되어 노드 간 진행률 갱신용으로 사용
- 위험: LangGraph 직렬화/체크포인트 기능 사용 시 직렬화 불가
- 권고: 체크포인터 도입 시 jobs를 State에서 제거하고 별도 컨텍스트로 전달

### concat 실패 묵음 처리
- 위치: pipeline.py:192 `except Exception: pass`
- 현황: 하이라이트 릴 concat 실패를 조용히 무시
- 권고: 최소한 logging.warning으로 기록

---

## 신규 노드 작성 가이드

1. 함수명 접두어 `node_` 사용: `async def node_xxx(state: PipelineState) -> dict`
2. 함수 첫 줄에 진행률 갱신: `_update(jobs, job_id, step="...", progress=N)`
3. 반환은 변경된 State 채널 키만 포함하는 dict
4. 새 채널이 필요하면 반드시 `PipelineState`에 타입 선언 추가
5. `_build_graph()` 내 `g.add_node()`와 `g.add_edge()` 동시 추가
6. fan-out 결과 누적 채널은 `Annotated[list, operator.add]` 타입으로 선언
7. asyncio.gather 사용 시 `return_exceptions=True` 고려 (fail-fast 방지)
