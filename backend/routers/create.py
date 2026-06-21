"""AI 완전 창작 숏폼 — API 라우터."""
import asyncio
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..models import CreateJob, JobStatus, ScriptData
from ..services.ai_creator import generate_script
from ..create_pipeline import run_create_pipeline

router = APIRouter(prefix="/api/create")

create_jobs: dict[str, CreateJob] = {}

CREATE_OUTPUT_DIR = Path("create_outputs")


# ── 요청 모델 ──────────────────────────────────────────────────────────

class ScriptRequest(BaseModel):
    prompt: str


class GenerateRequest(BaseModel):
    script: ScriptData


# ── 엔드포인트 ─────────────────────────────────────────────────────────

@router.post("/script")
async def create_script(body: ScriptRequest):
    """단일 프롬프트로 웹 검색 + 일관성 있는 장면별 스크립트를 생성한다."""
    if not body.prompt.strip():
        raise HTTPException(400, "프롬프트를 입력하세요.")
    return await generate_script(body.prompt.strip())


@router.post("/generate")
async def generate(body: GenerateRequest, background_tasks: BackgroundTasks):
    """스크립트를 받아 영상 생성 작업을 시작하고 job_id를 반환."""
    job_id = str(uuid.uuid4())
    job = CreateJob(id=job_id, title=body.script.title)
    create_jobs[job_id] = job

    CREATE_OUTPUT_DIR.mkdir(exist_ok=True)
    background_tasks.add_task(
        run_create_pipeline, job_id, body.script, CREATE_OUTPUT_DIR, create_jobs
    )
    return {"job_id": job_id}


@router.get("/jobs/{job_id}/events")
async def create_job_events(job_id: str):
    """SSE: 창작 작업 진행 상황 스트리밍."""
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


@router.get("/jobs/{job_id}")
async def get_create_job(job_id: str):
    job = create_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return job
