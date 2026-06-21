"""
AI 완전 창작 숏폼 파이프라인.
스크립트(ScriptData) → Nano Banana 이미지 + TTS → Veo 영상 생성 → ffmpeg 합성 → 자막 번인 → final.mp4

장면별 비주얼:
  image_prompt → Nano Banana(9:16 이미지) → Veo 3.1 Fast(이미지→영상, 9:16 클립)
Veo 실패/타임아웃 장면은 Nano Banana 이미지를 Ken Burns(슬로우 줌) 정지영상으로 폴백한다.
"""
import asyncio
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .models import JobStatus, ScriptData, CreateJob
from .services.tts_maker import generate_tts
from .services.shorts_maker import concat_shorts
from .services.caption_maker import _write_ass, _burn
from .services import veo_maker

# 동시 Veo 작업 수 제한 (쿼터/비용 가드)
VEO_CONCURRENCY = 2


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


def _update(jobs: dict, job_id: str, **kwargs):
    job = jobs[job_id]
    for k, v in kwargs.items():
        setattr(job, k, v)


def _save_meta(job_out: Path, job: CreateJob):
    meta = job.model_dump()
    with open(job_out / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


async def _process_scene(scene, job_out: Path, anchor_path: Path | None) -> tuple[Path, Path, float]:
    """장면 하나의 Nano Banana 이미지 + TTS를 병렬 생성. (tts_path, img_path, duration) 반환.
    anchor_path가 있으면 그 기준 이미지를 레퍼런스로 써서 화풍·인물·배경을 일관되게 유지한다."""
    tts_path = job_out / f"tts_{scene['order']}.mp3"
    img_path = job_out / f"img_{scene['order']}.png"

    if anchor_path is not None:
        img_prompt = (
            "Keep the exact same character, art style, color palette, lighting, and setting "
            f"as the reference image. New scene: {scene['image_prompt']}"
        )
    else:
        img_prompt = scene["image_prompt"]

    tts_duration, _ = await asyncio.gather(
        generate_tts(scene["narration"], tts_path),
        veo_maker.generate_image(img_prompt, img_path, reference_path=anchor_path),
    )

    return tts_path, img_path, tts_duration


async def _assemble_veo_clip(veo_path: Path, tts_path: Path, target: float, output_path: Path) -> None:
    """Veo 영상(무음) + TTS 오디오 → 나레이션 길이에 맞춘 9:16 클립.
    Veo 영상이 짧으면 마지막 프레임을 고정(tpad)해 늘리고, -t로 정확히 자른다."""
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        "tpad=stop_mode=clone:stop_duration=600,"
        "format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(veo_path),
        "-i", str(tts_path),
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-t", f"{target:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    result = await asyncio.to_thread(_run, cmd)
    if result.returncode != 0:
        raise RuntimeError(f"Veo clip assemble failed: {result.stderr.decode()[-400:]}")


async def _assemble_kenburns_clip(img_path: Path, tts_path: Path, target: float, output_path: Path) -> None:
    """폴백: Nano Banana 정지이미지 + TTS → Ken Burns(슬로우 줌) 9:16 클립."""
    frames = max(1, int(target * 30))
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        f"zoompan=z='min(zoom+0.0015,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s=1080x1920:fps=30,"
        "format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(img_path),
        "-i", str(tts_path),
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-t", f"{target:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    result = await asyncio.to_thread(_run, cmd)
    if result.returncode != 0:
        raise RuntimeError(f"Ken Burns clip failed: {result.stderr.decode()[-400:]}")


async def _make_scene_clip(
    scene: dict, img_path: Path, tts_path: Path, tts_duration: float,
    clip_path: Path, job_out: Path, sem: asyncio.Semaphore,
) -> tuple[bool, str]:
    """Veo로 장면 영상을 만들고 실패 시 Ken Burns 폴백. (veo_success, note) 반환."""
    target = max(1.0, tts_duration)
    veo_path = job_out / f"veo_{scene['order']}.mp4"
    duration = veo_maker.pick_duration(target)
    # Veo 모션 프롬프트: 장면 묘사 + 자연스러운 카메라/피사체 움직임 힌트
    veo_prompt = f"{scene['image_prompt']}. Subtle natural motion, gentle cinematic camera movement, smooth and realistic."

    try:
        async with sem:
            await veo_maker.generate_video(img_path, veo_prompt, duration, veo_path)
        await _assemble_veo_clip(veo_path, tts_path, target, clip_path)
        return True, "veo"
    except Exception as e:
        # Veo 실패 → 정지이미지 Ken Burns 폴백
        await _assemble_kenburns_clip(img_path, tts_path, target, clip_path)
        return False, f"fallback({type(e).__name__})"


def _build_ass_segments(scenes: list[dict], durations: list[float]) -> list[dict]:
    """ASS 자막 세그먼트 생성 (누적 타임스탬프 기반)."""
    segments = []
    t = 0.0
    for scene, dur in zip(scenes, durations):
        text = scene["narration"].strip()
        # 긴 나레이션은 중간에서 줄바꿈
        if len(text) > 18:
            mid = len(text) // 2
            cut = text.rfind(" ", mid - 6, mid + 8)
            if cut > 0:
                text = text[:cut] + "\\N" + text[cut + 1:]
        segments.append({"start": t, "end": t + dur, "text": text})
        t += dur
    return segments


async def run_create_pipeline(
    job_id: str, script: ScriptData, output_dir: Path, create_jobs: dict
):
    job_out = output_dir / job_id
    job_out.mkdir(parents=True, exist_ok=True)

    try:
        scenes = [s.model_dump() for s in script.scenes]

        # 0. 기준 이미지(anchor) 생성 — 전체 영상의 통일된 룩. 이후 모든 장면이 이를 레퍼런스로 사용.
        _update(
            create_jobs, job_id,
            status=JobStatus.PROCESSING,
            step="① 기준 이미지(화풍·인물·배경) 생성 중...",
            progress=8,
        )
        anchor_path = job_out / "anchor.png"
        style_prompt = getattr(script, "visual_style", "") or (scenes[0]["image_prompt"] if scenes else "")
        try:
            await veo_maker.generate_image(style_prompt, anchor_path)
        except Exception:
            # 기준 이미지 실패 시 레퍼런스 없이 진행(장면별 독립 생성)
            anchor_path = None

        # 1. 장면별 Nano Banana 이미지(기준 레퍼런스) + TTS 병렬 생성
        _update(
            create_jobs, job_id,
            step=f"② 장면 이미지 + 음성 생성 중 ({len(scenes)}개 장면)...",
            progress=18,
        )
        scene_results = await asyncio.gather(
            *[_process_scene(scene, job_out, anchor_path) for scene in scenes]
        )

        # 2. 장면별 Veo 영상 생성 (실패 시 Ken Burns 폴백)
        _update(
            create_jobs, job_id,
            step=f"② Veo 영상 생성 중 ({len(scenes)}개 장면, 시간이 걸립니다)...",
            progress=35,
        )
        sem = asyncio.Semaphore(VEO_CONCURRENCY)
        clip_paths = [job_out / f"scene_{i}.mp4" for i in range(len(scenes))]
        make_results = await asyncio.gather(*[
            _make_scene_clip(
                scenes[i], img_path, tts_path, dur, clip_paths[i], job_out, sem
            )
            for i, (tts_path, img_path, dur) in enumerate(scene_results)
        ])
        veo_ok = sum(1 for ok, _ in make_results if ok)

        # 3. 전체 concat
        _update(
            create_jobs, job_id,
            step=f"③ 장면 연결 중... (Veo {veo_ok}/{len(scenes)} 성공)",
            progress=72,
        )
        raw_path = job_out / "raw.mp4"
        await concat_shorts(clip_paths, raw_path)

        # 4. ASS 자막 생성 + 번인
        _update(create_jobs, job_id, step="④ 자막 합성 중...", progress=84)
        durations = [d for _, _, d in scene_results]
        ass_segments = _build_ass_segments(scenes, durations)
        ass_path = job_out / "subtitles.ass"
        _write_ass(ass_segments, ass_path)

        final_path = job_out / "final.mp4"
        result = await asyncio.to_thread(
            _burn, raw_path, ass_path.name, final_path, str(job_out)
        )
        ass_path.unlink(missing_ok=True)

        # 자막 번인 실패 시 raw를 final로 사용
        if result.returncode != 0 or not final_path.exists() or final_path.stat().st_size < 10_000:
            shutil.copy(raw_path, final_path)

        # 5. 썸네일 = 첫 번째 장면 이미지
        _update(create_jobs, job_id, step="⑤ 마무리 중...", progress=95)
        thumb_path = job_out / "thumbnail.jpg"
        first_img = scene_results[0][1]
        shutil.copy(first_img, thumb_path)

        _update(
            create_jobs, job_id,
            status=JobStatus.DONE,
            step="완료!",
            progress=100,
            video_url=f"/create_outputs/{job_id}/final.mp4",
            thumbnail_url=f"/create_outputs/{job_id}/thumbnail.jpg",
            completed_at=datetime.now().isoformat(),
        )
        _save_meta(job_out, create_jobs[job_id])

    except Exception as e:
        _update(
            create_jobs, job_id,
            status=JobStatus.ERROR,
            step="오류 발생",
            error=f"{type(e).__name__}: {e}" if str(e) else type(e).__name__,
        )
