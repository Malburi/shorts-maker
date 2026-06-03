"""
자막(캡션) 소각기 — Gemini 전사 세그먼트를 ASS 자막으로 변환해 영상에 태워넣기.
추가 AI 호출 없음; 전사 단계에서 받은 타임스탬프를 그대로 재사용.
"""
import asyncio
import subprocess
from pathlib import Path


def _run(cmd: list, cwd: str = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, cwd=cwd)


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _write_ass(segments: list, ass_path: Path):
    """TikTok/Reels 스타일 ASS 자막 파일 생성."""
    header = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Malgun Gothic,82,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1.5,0,1,6,2,2,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    lines = [header]
    for seg in segments:
        text = seg["text"].strip().replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{_fmt_time(seg['start'])},{_fmt_time(seg['end'])},Default,,0,0,0,,{text}"
        )
    # UTF-8 BOM — Windows ffmpeg libass가 BOM 없으면 한글 깨지는 경우 방지
    ass_path.write_text("\n".join(lines), encoding="utf-8-sig")


def _burn(clip_path: Path, ass_name: str, output_path: Path, work_dir: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(clip_path.resolve()),
            "-vf", f"ass={ass_name}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "copy",
            str(output_path.resolve()),
        ],
        capture_output=True,
        cwd=work_dir,
    )


async def add_captions(clip_path: Path, segments: list, clip_start: float, clip_end: float) -> Path:
    """
    전사 세그먼트를 클립 기준 상대 타임스탬프로 변환 후 ASS 자막을 소각.
    성공 시 clip_path를 자막 포함 버전으로 교체한다.
    """
    # 클립 구간에 걸치는 세그먼트만 추출, 시간 보정
    relevant = []
    for seg in segments:
        s0 = float(seg.get("start", 0))
        s1 = float(seg.get("end", 0))
        text = seg.get("text", "").strip()
        if not text or s1 <= clip_start or s0 >= clip_end:
            continue
        relevant.append({
            "start": max(0.0, s0 - clip_start),
            "end":   min(clip_end - clip_start, s1 - clip_start),
            "text":  text,
        })

    if not relevant:
        return clip_path  # 자막 없음 → 원본 유지

    work_dir = str(clip_path.parent)
    ass_path = clip_path.parent / f"{clip_path.stem}.ass"
    tmp_path = clip_path.parent / f"{clip_path.stem}_cap.mp4"

    _write_ass(relevant, ass_path)
    result = await asyncio.to_thread(_burn, clip_path, ass_path.name, tmp_path, work_dir)

    # 성공하면 원본 대체
    if result.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 10_000:
        clip_path.unlink(missing_ok=True)
        tmp_path.rename(clip_path)
    else:
        tmp_path.unlink(missing_ok=True)

    ass_path.unlink(missing_ok=True)
    return clip_path
