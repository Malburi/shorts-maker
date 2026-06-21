import asyncio
import json
import operator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .models import Job, JobStatus, KeyMoment, ShortResult
from .services.transcriber import extract_audio, transcribe
from .services.key_moments import select_key_moments
from .services.shorts_maker import make_short, get_video_duration, concat_shorts
from .services.caption_maker import add_captions
from .services.thumbnail_gen import make_thumbnail, extract_frame
from .services.rag import index_segments


# ── State ─────────────────────────────────────────────────────────────────────

class PipelineState(TypedDict):
    job_id: str
    video_path: str
    output_dir: str
    use_ai_thumbnail: bool
    jobs: Any  # dict[str, Job] — mutable reference, 노드 간 진행률 공유용

    duration: float
    has_knowledge: bool
    audio_path: str
    segments: list
    full_text: str
    moments: list
    results: Annotated[list, operator.add]  # fan-out 결과 누적
    highlight_reel_url: Optional[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _update(jobs: dict, job_id: str, **kwargs):
    job = jobs[job_id]
    for k, v in kwargs.items():
        setattr(job, k, v)


def _fallback_moments(duration: float) -> list[KeyMoment]:
    clip_len = min(60.0, max(30.0, duration / 3))
    moments, t, idx = [], 0.0, 0
    while t + 10 < duration and idx < 5:
        end = min(t + clip_len, duration)
        moments.append(KeyMoment(
            index=idx, title=f"하이라이트 {idx + 1}",
            start=round(t, 1), end=round(end, 1),
            reason="핵심 없음 — 시간 균등 분할",
        ))
        t = end
        idx += 1
    return moments


def _save_meta(job_out: Path, job: Job):
    meta = job.model_dump()
    with open(job_out / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def node_get_duration(state: PipelineState) -> dict:
    jobs, job_id = state["jobs"], state["job_id"]
    _update(jobs, job_id, status=JobStatus.PROCESSING, step="영상 길이 확인 중...", progress=5)

    duration = await get_video_duration(Path(state["video_path"]))
    if duration <= 0:
        raise ValueError("영상 길이를 읽을 수 없습니다.")
    _update(jobs, job_id, video_duration=round(duration, 1))
    return {"duration": duration}


async def node_extract_audio(state: PipelineState) -> dict:
    jobs, job_id = state["jobs"], state["job_id"]
    _update(jobs, job_id, step="오디오 추출 중...", progress=10)

    job_out = Path(state["output_dir"]) / job_id
    job_out.mkdir(parents=True, exist_ok=True)
    audio_path = job_out / "audio.mp3"
    await extract_audio(Path(state["video_path"]), audio_path)
    return {"audio_path": str(audio_path)}


async def node_transcribe(state: PipelineState) -> dict:
    jobs, job_id = state["jobs"], state["job_id"]
    _update(jobs, job_id, step="① AI 전사 중 (Whisper)...", progress=25)

    transcript_data = await transcribe(Path(state["audio_path"]))
    segments = transcript_data.get("segments", [])
    full_text = transcript_data.get("text", "")
    preview = full_text[:200] + ("..." if len(full_text) > 200 else "") if full_text else ""
    _update(jobs, job_id, transcript_preview=preview)
    return {"segments": segments, "full_text": full_text}


async def node_index_knowledge(state: PipelineState) -> dict:
    """전사 세그먼트를 ChromaDB에 임베딩 & 저장."""
    jobs, job_id = state["jobs"], state["job_id"]
    _update(jobs, job_id, step="② 지식 베이스 구축 중 (RAG 인덱싱)...", progress=33)
    await index_segments(job_id, state["segments"])
    _update(jobs, job_id, has_knowledge=True)
    return {"has_knowledge": True}


async def node_select_moments(state: PipelineState) -> dict:
    jobs, job_id = state["jobs"], state["job_id"]
    _update(jobs, job_id, step="③ AI 핵심 장면 선정 중 (Gemini 2.5 Flash)...", progress=42)

    moments = await select_key_moments(state["segments"], state["duration"])
    if not moments:
        moments = _fallback_moments(state["duration"])
    _update(jobs, job_id, key_moments=moments)
    return {"moments": moments}


def node_dispatch_clips(state: PipelineState):
    """Fan-out: 각 핵심 장면을 node_process_clip으로 병렬 분기."""
    _update(state["jobs"], state["job_id"],
            step=f"쇼츠 {len(state['moments'])}개 생성 중 (ffmpeg + 자막)...", progress=55)
    return [
        Send("node_process_clip", {
            "moment": m,
            "job_id": state["job_id"],
            "video_path": state["video_path"],
            "output_dir": state["output_dir"],
            "segments": state["segments"],
            "use_ai_thumbnail": state["use_ai_thumbnail"],
        })
        for m in state["moments"]
    ]


async def node_process_clip(payload: dict) -> dict:
    """단일 클립 처리: 원본 프레임 캡처 → 쇼츠 생성 → 자막 번인 → 썸네일."""
    moment: KeyMoment = payload["moment"]
    job_id: str = payload["job_id"]
    video_path = Path(payload["video_path"])
    job_out = Path(payload["output_dir"]) / job_id
    segments = payload["segments"]
    use_ai = payload["use_ai_thumbnail"]

    clip_path = job_out / f"short_{moment.index}.mp4"
    thumb_path = job_out / f"thumb_{moment.index}.jpg"
    preview_path = job_out / f"preview_{moment.index}.jpg"

    # 원본 영상 중간 지점에서 하이라이트 프레임 캡처
    preview_seek = moment.start + (moment.end - moment.start) * 0.5
    await extract_frame(video_path, preview_seek, preview_path)

    await make_short(video_path, moment, clip_path)
    await add_captions(clip_path, segments, moment.start, moment.end)

    clip_duration = moment.end - moment.start
    await make_thumbnail(clip_path, clip_duration, moment.title, moment.reason, thumb_path, use_ai=use_ai)

    return {"results": [ShortResult(
        index=moment.index,
        title=moment.title,
        reason=moment.reason,
        video_url=f"/outputs/{job_id}/short_{moment.index}.mp4",
        thumbnail_url=f"/outputs/{job_id}/thumb_{moment.index}.jpg",
        duration=round(clip_duration, 1),
        clip_start=moment.start,
        clip_end=moment.end,
        preview_frame_url=f"/outputs/{job_id}/preview_{moment.index}.jpg" if preview_path.exists() else None,
    )]}


async def node_concat_highlight(state: PipelineState) -> dict:
    jobs, job_id = state["jobs"], state["job_id"]
    _update(jobs, job_id, step="하이라이트 릴 합치는 중...", progress=88)

    job_out = Path(state["output_dir"]) / job_id
    results = sorted(state["results"], key=lambda r: r.index)
    _update(jobs, job_id, shorts=results)

    highlight_reel_url = None
    try:
        ordered_moments = sorted(state["moments"], key=lambda m: m.start)
        clip_paths = [job_out / f"short_{m.index}.mp4" for m in ordered_moments]
        highlight_path = job_out / "highlight_reel.mp4"
        await concat_shorts(clip_paths, highlight_path)
        highlight_reel_url = f"/outputs/{job_id}/highlight_reel.mp4"
    except Exception:
        pass  # concat 실패해도 개별 클립은 정상 제공

    return {"highlight_reel_url": highlight_reel_url}


async def node_finalize(state: PipelineState) -> dict:
    jobs, job_id = state["jobs"], state["job_id"]
    job_out = Path(state["output_dir"]) / job_id

    _update(jobs, job_id,
            status=JobStatus.DONE, step="완료!", progress=100,
            highlight_reel_url=state["highlight_reel_url"],
            completed_at=datetime.now().isoformat())
    _save_meta(job_out, jobs[job_id])
    return {}


# ── Graph ─────────────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    g = StateGraph(PipelineState)

    g.add_node("node_get_duration", node_get_duration)
    g.add_node("node_extract_audio", node_extract_audio)
    g.add_node("node_transcribe", node_transcribe)
    g.add_node("node_index_knowledge", node_index_knowledge)
    g.add_node("node_select_moments", node_select_moments)
    g.add_node("node_process_clip", node_process_clip)
    g.add_node("node_concat_highlight", node_concat_highlight)
    g.add_node("node_finalize", node_finalize)

    g.add_edge(START, "node_get_duration")
    g.add_edge("node_get_duration", "node_extract_audio")
    g.add_edge("node_extract_audio", "node_transcribe")
    g.add_edge("node_transcribe", "node_index_knowledge")
    g.add_edge("node_index_knowledge", "node_select_moments")
    g.add_conditional_edges("node_select_moments", node_dispatch_clips, ["node_process_clip"])
    g.add_edge("node_process_clip", "node_concat_highlight")
    g.add_edge("node_concat_highlight", "node_finalize")
    g.add_edge("node_finalize", END)

    return g.compile()


_graph = _build_graph()


# ── Entry Point ───────────────────────────────────────────────────────────────

async def run_pipeline(job_id: str, video_path: Path, output_dir: Path, jobs: dict, use_ai_thumbnail: bool = True):
    try:
        await _graph.ainvoke({
            "job_id": job_id,
            "video_path": str(video_path),
            "output_dir": str(output_dir),
            "use_ai_thumbnail": use_ai_thumbnail,
            "jobs": jobs,
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
