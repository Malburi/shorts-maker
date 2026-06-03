import uuid
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# ffmpeg winget 설치 경로를 PATH에 추가
_FFMPEG_WINGET = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages"
for _p in _FFMPEG_WINGET.glob("Gyan.FFmpeg*/*/bin"):
    os.environ["PATH"] = str(_p) + os.pathsep + os.environ.get("PATH", "")
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from .models import Job, JobStatus
from .pipeline import run_pipeline

app = FastAPI(title="Shorts Maker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

jobs: dict[str, Job] = {}

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


@app.post("/api/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    ai_thumbnail: bool = Query(default=True, description="AI 썸네일 생성 여부"),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"지원하지 않는 형식입니다. ({', '.join(ALLOWED_EXTENSIONS)})")

    job_id = str(uuid.uuid4())
    video_path = UPLOAD_DIR / f"{job_id}{ext}"

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "파일 크기는 500MB 이하여야 합니다.")
    if len(content) == 0:
        raise HTTPException(400, "빈 파일입니다.")

    with open(video_path, "wb") as f:
        f.write(content)

    job = Job(id=job_id, filename=file.filename or "video")
    jobs[job_id] = job

    background_tasks.add_task(run_pipeline, job_id, video_path, OUTPUT_DIR, jobs, ai_thumbnail)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return job


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    """SSE endpoint for real-time job progress."""
    if job_id not in jobs:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")

    async def event_stream():
        while True:
            job = jobs.get(job_id)
            if not job:
                break
            data = job.model_dump_json()
            yield f"data: {data}\n\n"
            if job.status in (JobStatus.DONE, JobStatus.ERROR):
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/api/history/{job_id}", status_code=204)
async def delete_job(job_id: str):
    import shutil, re
    if not re.fullmatch(r"[0-9a-f\-]{36}", job_id):
        raise HTTPException(400, "잘못된 job_id입니다.")
    job_dir = OUTPUT_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    shutil.rmtree(job_dir, ignore_errors=True)
    jobs.pop(job_id, None)


@app.get("/api/history")
async def get_history():
    """Return all completed jobs from disk, newest first."""
    import json as _json
    items = []
    for meta_file in sorted(OUTPUT_DIR.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(meta_file, encoding="utf-8") as f:
                items.append(_json.load(f))
        except Exception:
            pass
    return items


@app.get("/api/health")
async def health():
    return {"status": "ok"}
