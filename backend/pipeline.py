import asyncio
import json
from datetime import datetime
from pathlib import Path
from .models import Job, JobStatus, KeyMoment, ShortResult
from .services.transcriber import extract_audio, transcribe
from .services.key_moments import select_key_moments
from .services.shorts_maker import make_short, get_video_duration, concat_shorts
from .services.caption_maker import add_captions
from .services.thumbnail_gen import make_thumbnail


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


async def run_pipeline(job_id: str, video_path: Path, output_dir: Path, jobs: dict, use_ai_thumbnail: bool = True):
    job_out = output_dir / job_id
    job_out.mkdir(parents=True, exist_ok=True)

    try:
        _update(jobs, job_id, status=JobStatus.PROCESSING, step="영상 길이 확인 중...", progress=5)

        # 1. 영상 길이
        duration = await get_video_duration(video_path)
        if duration <= 0:
            raise ValueError("영상 길이를 읽을 수 없습니다.")
        _update(jobs, job_id, video_duration=round(duration, 1))

        # 2. 오디오 추출
        _update(jobs, job_id, step="오디오 추출 중...", progress=10)
        audio_path = job_out / "audio.mp3"
        await extract_audio(video_path, audio_path)

        # 3. Whisper 전사
        _update(jobs, job_id, step="① AI 전사 중 (Whisper)...", progress=25)
        transcript_data = await transcribe(audio_path)
        segments = transcript_data.get("segments", [])
        full_text = transcript_data.get("text", "")
        preview = ""
        if full_text and len(full_text) < 2000:
            preview = full_text[:200] + ("..." if len(full_text) > 200 else "")
        _update(jobs, job_id, transcript_preview=preview)

        # 4. Gemini 핵심 장면 선정
        _update(jobs, job_id, step="② AI 핵심 장면 선정 중 (Gemini 2.5 Flash)...", progress=40)
        moments = await select_key_moments(segments, duration)
        if not moments:
            moments = _fallback_moments(duration)
        _update(jobs, job_id, key_moments=moments)

        # 5. 클립 생성 + 자막 번인 + 썸네일 (병렬)
        _update(jobs, job_id, step=f"쇼츠 {len(moments)}개 생성 중 (ffmpeg + 자막)...", progress=55)

        async def process_one(moment):
            clip_path = job_out / f"short_{moment.index}.mp4"
            thumb_path = job_out / f"thumb_{moment.index}.jpg"

            await make_short(video_path, moment, clip_path)
            await add_captions(clip_path, segments, moment.start, moment.end)

            clip_duration = moment.end - moment.start
            await make_thumbnail(
                clip_path, clip_duration,
                moment.title, moment.reason,
                thumb_path, use_ai=use_ai_thumbnail,
            )
            return ShortResult(
                index=moment.index,
                title=moment.title,
                reason=moment.reason,
                video_url=f"/outputs/{job_id}/short_{moment.index}.mp4",
                thumbnail_url=f"/outputs/{job_id}/thumb_{moment.index}.jpg",
                duration=round(moment.end - moment.start, 1),
                clip_start=moment.start,
                clip_end=moment.end,
            )

        results = await asyncio.gather(*[process_one(m) for m in moments])
        results = sorted(results, key=lambda r: r.index)

        # Concat highlight reel (clips in timeline order)
        highlight_reel_url = None
        try:
            _update(jobs, job_id, step="하이라이트 릴 합치는 중...", progress=88)
            ordered_clips = [job_out / f"short_{m.index}.mp4" for m in sorted(moments, key=lambda m: m.start)]
            highlight_path = job_out / "highlight_reel.mp4"
            await concat_shorts(ordered_clips, highlight_path)
            highlight_reel_url = f"/outputs/{job_id}/highlight_reel.mp4"
        except Exception as e:
            pass  # concat 실패해도 개별 클립은 정상 제공

        _update(jobs, job_id,
                status=JobStatus.DONE, step="완료!",  progress=100,
                shorts=list(results),
                highlight_reel_url=highlight_reel_url,
                completed_at=datetime.now().isoformat())

        _save_meta(job_out, jobs[job_id])

    except Exception as e:
        _update(jobs, job_id,
                status=JobStatus.ERROR, step="오류 발생",
                error=f"{type(e).__name__}: {e}" if str(e) else type(e).__name__)
