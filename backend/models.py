from pydantic import BaseModel
from enum import Enum
from typing import Optional, List


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


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
