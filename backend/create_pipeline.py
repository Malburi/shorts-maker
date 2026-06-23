"""
AI 완전 창작 숏폼 파이프라인.
스크립트(ScriptData) → Nano Banana 시작 이미지 + TTS → Veo 순차 체이닝 → ffmpeg 합성 → 자막 번인 → final.mp4

비주얼 (마지막 프레임 이어받기 = 한 컷처럼 자연스러운 연속 영상):
  1번 클립:  scene1 image_prompt → Nano Banana(9:16 이미지) → Veo 3.1 Fast(이미지→영상)
  N번 클립:  직전 클립의 마지막 프레임 → Veo(이미지→영상)  ← 화면이 끊김 없이 이어짐
Veo는 1회 최대 8초라 30~60초는 여러 클립이 필요하지만, 경계 프레임이 동일해 concat 시 이음새가 없다.
각 클립 Veo 실패/타임아웃은 그 입력 이미지를 Ken Burns(슬로우 줌) 정지영상으로 폴백한다.
"""
import asyncio
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .models import JobStatus, ScriptData, CreateJob
from .services.tts_maker import generate_tts
from .services.caption_maker import _write_ass, _burn
from .services import veo_maker

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


def _anchored_image_prompt(scene: dict, anchor_path: Path | None) -> str:
    """기준 이미지(anchor)가 있으면 화풍·인물·배경을 그대로 유지하라는 지시를 덧붙인다."""
    if anchor_path is not None:
        return (
            "Keep the exact same character, art style, color palette, lighting, and setting "
            f"as the reference image. New scene: {scene['image_prompt']}"
        )
    return scene["image_prompt"]


def _extract_last_frame_sync(clip_path: Path, out_png: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-sseof", "-1", "-i", str(clip_path),
        "-update", "1", "-frames:v", "1", "-q:v", "2",
        str(out_png),
    ]
    result = _run(cmd)
    if result.returncode != 0 or not out_png.exists():
        raise RuntimeError(f"마지막 프레임 추출 실패: {result.stderr.decode()[-300:]}")


async def _extract_last_frame(clip_path: Path, out_png: Path) -> Path:
    """클립의 마지막 프레임을 PNG로 추출 — 다음 Veo 클립의 시작 이미지로 사용한다."""
    await asyncio.to_thread(_extract_last_frame_sync, clip_path, out_png)
    return out_png


async def _assemble_veo_clip(veo_path: Path, tts_path: Path, target: float, output_path: Path) -> None:
    """Veo 영상(무음) + TTS 오디오 → 나레이션 길이에 맞춘 9:16 클립.
    Veo 영상이 짧으면 마지막 프레임을 고정(tpad)해 늘리고, -t로 정확히 자른다."""
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        "tpad=stop_mode=clone:stop_duration=600,"
        "fps=30,format=yuv420p"  # Ken Burns 폴백(30fps)과 fps 통일 → concat 시 영상 흔들림 방지
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


async def _concat_reencode(clip_paths: list[Path], output_path: Path) -> None:
    """클립들을 '재인코딩'하며 이어붙인다. `-c copy` 대신 한 번에 다시 인코딩하므로
    (1) 클립마다 따로 인코딩된 AAC의 인코더 지연(priming)으로 생기는 오디오 싱크 드리프트와
    (2) 클립 간 fps 불일치로 생기는 영상 흔들림을 모두 제거한다. (창작 모드 전용)"""
    list_path = output_path.parent / "concat_list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-fps_mode", "cfr", "-r", "30",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-af", "aresample=async=1:first_pts=0",
        "-movflags", "+faststart",
        str(output_path),
    ]
    result = await asyncio.to_thread(_run, cmd)
    list_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"concat(재인코딩) 실패: {result.stderr.decode()[-400:]}")


async def _make_scene_clip(
    scene: dict, input_img: Path, tts_path: Path, tts_duration: float,
    clip_path: Path, job_out: Path, continued: bool,
) -> tuple[bool, str]:
    """input_img(시작 이미지 또는 직전 클립의 마지막 프레임)에서 Veo 영상을 만들고
    실패 시 Ken Burns 폴백. (veo_success, note) 반환.
    continued=True면 직전 화면에서 자연스럽게 이어지도록 프롬프트를 보강한다."""
    target = max(1.0, tts_duration)
    veo_path = job_out / f"veo_{scene['order']}.mp4"
    duration = veo_maker.pick_duration(target)
    cont = (
        " Continuing smoothly from the current frame, keeping the same character, "
        "art style, color palette, lighting and setting." if continued else ""
    )
    # Veo 모션 프롬프트: 장면 묘사 + (이어받기 시) 연속 전환 + 자연스러운 움직임 힌트
    veo_prompt = (
        f"{scene['image_prompt']}.{cont} "
        "Subtle natural motion, gentle cinematic camera movement, smooth and realistic."
    )

    try:
        await veo_maker.generate_video(input_img, veo_prompt, duration, veo_path)
        await _assemble_veo_clip(veo_path, tts_path, target, clip_path)
        return True, "veo"
    except Exception as e:
        # Veo 실패 → 정지이미지 Ken Burns 폴백
        await _assemble_kenburns_clip(input_img, tts_path, target, clip_path)
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

        # 1a. 시작 이미지(1번 장면)만 Nano Banana로 생성. 나머지 구간은 직전 클립의
        #     마지막 프레임을 이어받으므로 별도 이미지 생성이 필요 없다(비용 절감).
        _update(
            create_jobs, job_id,
            step="② 시작 이미지 생성 중...",
            progress=14,
        )
        scene1_img = job_out / f"img_{scenes[0]['order']}.png"
        try:
            await veo_maker.generate_image(
                _anchored_image_prompt(scenes[0], anchor_path),
                scene1_img,
                reference_path=anchor_path,
            )
        except Exception:
            # 시작 이미지 실패 → 기준 이미지를 그대로 사용(그것도 없으면 예외 전파)
            if anchor_path is not None and anchor_path.exists():
                shutil.copy(anchor_path, scene1_img)
            else:
                raise

        # 1b. 전 구간 TTS 병렬 생성 (각 클립 길이를 결정)
        _update(
            create_jobs, job_id,
            step=f"② 음성(나레이션) 생성 중 ({len(scenes)}개 구간)...",
            progress=20,
        )
        tts_paths = [job_out / f"tts_{s['order']}.mp3" for s in scenes]
        durations = list(await asyncio.gather(
            *[generate_tts(s["narration"], tts_paths[i]) for i, s in enumerate(scenes)]
        ))

        # 2. Veo 순차 체이닝: 클립 N은 클립 N-1의 마지막 프레임에서 이어 생성한다.
        #    경계가 동일 프레임이라 concat 시 한 컷처럼 자연스럽게 이어진다.
        #    (각 구간 Veo 실패 시 Ken Burns 폴백 → 부분 실패가 전체를 죽이지 않음)
        clip_paths = [job_out / f"scene_{i}.mp4" for i in range(len(scenes))]
        prev_frame: Path | None = None
        veo_ok = 0
        for i, scene in enumerate(scenes):
            _update(
                create_jobs, job_id,
                step=f"② Veo 영상 생성·이어붙이는 중 (장면 {i + 1}/{len(scenes)})...",
                progress=30 + int(42 * i / max(1, len(scenes))),
            )
            input_img = scene1_img if i == 0 else prev_frame
            ok, note = await _make_scene_clip(
                scene, input_img, tts_paths[i], durations[i],
                clip_paths[i], job_out, continued=(i > 0),
            )
            if ok:
                veo_ok += 1
            else:
                # Veo 실패 → 정지 Ken Burns 폴백. 사유를 로그에 남겨 진단 가능하게.
                print(f"[create] scene {i + 1}/{len(scenes)} Veo 실패 → {note}", flush=True)
            # 다음 클립이 이어받을 마지막 프레임 추출 (마지막 장면은 불필요)
            if i < len(scenes) - 1:
                frame_png = job_out / f"lastframe_{i}.png"
                try:
                    prev_frame = await _extract_last_frame(clip_paths[i], frame_png)
                except Exception:
                    # 추출 실패 시 시작 이미지로 폴백(연속성↓, 진행은 계속)
                    prev_frame = scene1_img

        # 3. 전체 concat
        _update(
            create_jobs, job_id,
            step=f"③ 장면 연결 중... (Veo {veo_ok}/{len(scenes)} 성공)",
            progress=72,
        )
        raw_path = job_out / "raw.mp4"
        await _concat_reencode(clip_paths, raw_path)

        # 4. ASS 자막 생성 + 번인
        _update(create_jobs, job_id, step="④ 자막 합성 중...", progress=84)
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
        shutil.copy(scene1_img, thumb_path)

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
