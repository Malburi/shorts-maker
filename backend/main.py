import uuid
import asyncio
import os
import re
import subprocess
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
from pydantic import BaseModel as PydanticBaseModel
from .models import Job, JobStatus
from .pipeline import run_pipeline
from .routers.create import router as create_router
from .services.rag import query as rag_query

app = FastAPI(title="Shorts Maker API")
app.include_router(create_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
CREATE_OUTPUT_DIR = Path("create_outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CREATE_OUTPUT_DIR.mkdir(exist_ok=True)

app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/create_outputs", StaticFiles(directory=str(CREATE_OUTPUT_DIR)), name="create_outputs")

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


_YT_PATTERN = re.compile(
    r"(youtube\.com/(watch\?.*v=|shorts/)|youtu\.be/)[A-Za-z0-9_\-]+"
)


class YoutubeRequest(PydanticBaseModel):
    url: str
    ai_thumbnail: bool = True


async def _download_and_run(job_id: str, url: str, video_path: Path, ai_thumbnail: bool):
    job = jobs[job_id]
    try:
        job.step = "YouTube 영상 다운로드 중..."
        job.status = JobStatus.PROCESSING
        job.progress = 2

        result = await asyncio.to_thread(
            subprocess.run,
            [
                "yt-dlp",
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "-o", str(video_path),
                url,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:300] or "yt-dlp 다운로드 실패")

        await run_pipeline(job_id, video_path, OUTPUT_DIR, jobs, ai_thumbnail)
    except Exception as exc:
        job.status = JobStatus.ERROR
        job.error = str(exc)


@app.post("/api/youtube")
async def download_youtube(body: YoutubeRequest, background_tasks: BackgroundTasks):
    if not _YT_PATTERN.search(body.url):
        raise HTTPException(400, "YouTube URL이 아닙니다. (youtube.com 또는 youtu.be 링크를 입력하세요)")

    job_id = str(uuid.uuid4())
    video_path = UPLOAD_DIR / f"{job_id}.mp4"

    # Extract video title from URL for display
    video_id = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_\-]{11})", body.url)
    filename = f"youtube_{video_id.group(1)}.mp4" if video_id else "youtube_video.mp4"

    job = Job(id=job_id, filename=filename)
    jobs[job_id] = job

    background_tasks.add_task(_download_and_run, job_id, body.url, video_path, body.ai_thumbnail)
    return {"job_id": job_id}


class ChatRequest(PydanticBaseModel):
    question: str


@app.post("/api/jobs/{job_id}/chat")
async def chat_with_video(job_id: str, body: ChatRequest):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    if not job.has_knowledge:
        raise HTTPException(400, "지식 베이스가 아직 준비되지 않았습니다.")
    return await rag_query(job_id, body.question)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
