from pydantic import BaseModel
from enum import Enum
from typing import Optional, List


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


# ── AI 창작 숏폼 모델 ──────────────────────────────────────────────────

class ContentOutline(BaseModel):
    title_idea: str
    hook: str
    key_points: List[str]
    closing: str
    tone_note: str


class ScriptScene(BaseModel):
    order: int
    narration: str
    image_prompt: str


class ScriptData(BaseModel):
    title: str
    target_duration: int = 60
    # 전체 영상의 통일된 비주얼 기준 (화풍·색감·조명·등장 인물/피사체·배경).
    # 기준 이미지 생성 + 각 장면 이미지의 레퍼런스 일관성 유지에 사용된다.
    visual_style: str = ""
    scenes: List[ScriptScene]


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


class KeyMoment(BaseModel):
    index: int
    title: str
    start: float
    end: float
    reason: str


class ShortResult(BaseModel):
    index: int
    title: str
    reason: str
    video_url: str
    thumbnail_url: str
    duration: float
    clip_start: float = 0.0
    clip_end: float = 0.0
    preview_frame_url: Optional[str] = None


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
