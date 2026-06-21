"""
실행: python draw_graph.py
결과: pipeline_graph.png 생성
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

_FFMPEG = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Packages"
for _p in _FFMPEG.glob("Gyan.FFmpeg*/*/bin"):
    os.environ["PATH"] = str(_p) + os.pathsep + os.environ.get("PATH", "")

sys.path.insert(0, str(Path(__file__).parent))
from backend.pipeline import _graph

# PNG 저장
png = _graph.get_graph().draw_mermaid_png()
with open("pipeline_graph.png", "wb") as f:
    f.write(png)
print("pipeline_graph.png 저장 완료")

# ASCII도 출력
print(_graph.get_graph().draw_ascii())
