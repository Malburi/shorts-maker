# Model / Schema Pattern — Shorts Maker

추출 시각: 2026-06-17
샘플 파일 수: 1 (backend/models.py 전체 + 사용처 확인)
신뢰도: HIGH (단일 파일, 전 모델 통독)

---

## 권장 패턴

### Pydantic v2 모델 정의 스타일
빈도: 100% (7/7 모델)

```python
from pydantic import BaseModel
from enum import Enum
from typing import Optional, List

class MyModel(BaseModel):
    id: str
    name: str = ""                    # 문자열 기본값 빈 문자열
    status: JobStatus = JobStatus.PENDING
    progress: int = 0                 # 정수 기본값 0
    error: Optional[str] = None       # Optional은 None 기본값
    items: List[SomeModel] = []       # 리스트는 [] 기본값 (default_factory 미사용)
    completed_at: str = ""            # datetime 대신 ISO 문자열
```

규칙:
- `BaseModel` (pydantic v2) 직접 상속 (`model_config` 미사용)
- 검증 어노테이션(`@validator`, `@field_validator`) 없음 — 단순 타입 선언만
- `datetime` 타입 미사용 — `completed_at: str = ""` 로 ISO 문자열 저장
- `default_factory` 미사용 — `List[X] = []` 직접 선언 (v2에서는 허용)

---

### Enum 정의 — JobStatus
빈도: 단일, 전 파이프라인에서 사용

```python
class JobStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    DONE       = "done"
    ERROR      = "error"
```

- `str, Enum` 다중 상속 → JSON 직렬화 시 문자열 값 그대로 출력 (예: `"pending"`)
- 프론트엔드 비교: `job.value.status === 'done'` (소문자)

---

### Job 모델 (업로드 파이프라인)

```python
class Job(BaseModel):
    id: str
    filename: str = ""
    status: JobStatus = JobStatus.PENDING
    step: str = "대기 중"
    progress: int = 0
    error: Optional[str] = None
    transcript_preview: str = ""
    key_moments: List[KeyMoment] = []
    shorts: List[ShortResult] = []
    video_duration: float = 0.0
    completed_at: str = ""
    highlight_reel_url: Optional[str] = None
    has_knowledge: bool = False
```

SSE 페이로드: `job.model_dump_json()` — 전체 필드 직렬화.

---

### CreateJob 모델 (AI 창작 파이프라인)

```python
class CreateJob(BaseModel):
    id: str
    title: str = ""
    status: JobStatus = JobStatus.PENDING
    step: str = "대기 중"
    progress: int = 0
    error: Optional[str] = None
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    completed_at: str = ""
```

Job과 비교: `key_moments`, `shorts`, `video_duration`, `has_knowledge` 없음. 창작 모드 전용 필드 `video_url`, `thumbnail_url` 추가.

---

### 중첩 모델 구조

```python
# Job → List[KeyMoment]
class KeyMoment(BaseModel):
    index: int
    title: str
    start: float      # 초 단위 타임스탬프
    end: float
    reason: str

# Job → List[ShortResult]
class ShortResult(BaseModel):
    index: int
    title: str
    reason: str
    video_url: str                       # /outputs/{job_id}/short_{index}.mp4
    thumbnail_url: str                   # /outputs/{job_id}/thumb_{index}.jpg
    duration: float
    clip_start: float = 0.0
    clip_end: float = 0.0
    preview_frame_url: Optional[str] = None   # 원본 프레임 (AI 썸네일 비교용)

# ScriptData → List[ScriptScene]
class ScriptData(BaseModel):
    title: str
    target_duration: int = 60           # 초 단위 목표 길이
    scenes: List[ScriptScene]

class ScriptScene(BaseModel):
    order: int
    narration: str                       # 한국어 TTS 나레이션
    image_prompt: str                    # 영어 이미지 생성 프롬프트
```

---

### URL 필드 규약

URL 필드는 정적 파일 서버 상대경로 (절대 URL 아님):
```python
video_url   = f"/outputs/{job_id}/short_{index}.mp4"
thumbnail_url = f"/outputs/{job_id}/thumb_{index}.jpg"
video_url   = f"/create_outputs/{job_id}/final.mp4"
thumbnail_url = f"/create_outputs/{job_id}/thumbnail.jpg"
```

Vite proxy가 `/outputs`, `/create_outputs` → `localhost:8000` 로 중계.

---

### 인라인 요청 모델 (라우터 파일)

models.py 외부에도 인라인 요청 모델이 존재:

```python
# main.py
class YoutubeRequest(PydanticBaseModel):   # ← PydanticBaseModel 별칭 사용
    url: str
    ai_thumbnail: bool = True

class ChatRequest(PydanticBaseModel):
    question: str

# routers/create.py
class AnswerItem(BaseModel):
    question: str
    answer: str

class InterviewRequest(BaseModel):
    topic: str
    answers: list[AnswerItem] = []

class ScriptRequest(BaseModel):
    topic: str
    answers: list[AnswerItem] = []
    outline: ContentOutline
    search_context: str = ""

class GenerateRequest(BaseModel):
    script: ScriptData
```

main.py에서 `from pydantic import BaseModel as PydanticBaseModel` 별칭 사용 — models.py의 BaseModel과 충돌 방지용.

---

## 안티패턴 (피해야 할 패턴)

### completed_at을 빈 문자열 초기값으로 사용
- 현황: `completed_at: str = ""` — 미완료 시 빈 문자열, 완료 시 ISO 문자열
- 권고: `Optional[str] = None` 으로 미완료/완료를 명확히 구분

### datetime 미사용 — 시간 비교 불가
- 현황: `datetime.now().isoformat()` 으로 문자열 저장 → 정렬은 문자열 비교
- 현재는 `sorted(..., key=lambda p: p.stat().st_mtime)` 으로 파일 수정시각 기준 정렬 (실용적)
- 권고: API 확장 시 datetime 타입 도입 고려

### List[X] = [] 기본값 — 공유 인스턴스 위험
- 현황: `key_moments: List[KeyMoment] = []`
- Pydantic v2는 내부적으로 default_factory로 처리하므로 실제 공유 없음 — 현재 코드 안전
- 명시적으로 쓰려면: `key_moments: List[KeyMoment] = Field(default_factory=list)`

---

## 신규 모델 작성 가이드

1. 전역 공유 모델 → `backend/models.py`에 추가
2. 라우터 전용 요청 모델 → 해당 라우터 파일 상단에 인라인 정의
3. 필드 기본값 규칙:
   - 문자열: `= ""`
   - 정수/실수: `= 0` / `= 0.0`
   - 불리언: `= False`
   - 리스트: `= []`
   - 선택적 값: `Optional[T] = None`
4. Status Enum은 `str, Enum` 다중 상속 패턴 유지 (JSON 직렬화 호환)
5. 타임스탬프는 현재 컨벤션(ISO 문자열)을 따르거나, 신규라면 `Optional[str] = None`
6. URL 필드는 `/outputs/` 또는 `/create_outputs/` 접두사 상대경로 규칙 준수
