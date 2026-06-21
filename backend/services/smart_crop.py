"""
스마트 크롭: 가로 영상을 9:16 세로로 변환할 때 핵심 피사체를 감지해
크롭 창을 그 쪽으로 이동시킨다. 장르를 가리지 않도록 자동 다단계로 동작한다.

감지 우선순위 (앞 단계가 실패하면 다음 단계로):
  1) 얼굴   — OpenCV Haar cascade (정면+측면). 인물/토킹헤드.
  2) 움직임 — 프레임 차분의 열(column) 분포 중심. 스포츠 공·게임 캐릭터·액션 등
              "움직이는 주 피사체"를 클래스 무관하게 추적.
  3) 세일런시 — 엣지/디테일 밀집도(Laplacian)의 열 중심. 정지 장면의 주 피사체.
  4) 모두 실패 → None → 호출부가 레터박스(풀샷 + 위아래 검은 여백) 폴백.

opencv-python(+numpy)만 사용하므로 별도 모델 다운로드/무거운 의존성이 없다.
import/감지 실패는 모두 None으로 흡수해 파이프라인이 죽지 않도록 한다.
"""
from pathlib import Path
from statistics import median

TARGET_W = 1080
TARGET_H = 1920
TARGET_RATIO = TARGET_W / TARGET_H  # 9:16 = 0.5625

# 샘플링 설정
SAMPLE_INTERVAL = 0.5   # 초 간격으로 프레임 샘플링
MAX_SAMPLES = 20        # 클립당 최대 샘플 수 (처리 시간 가드)

# 움직임/세일런시 임계값 — 신호가 약하거나 평탄하면 다음 단계/레터박스로 넘긴다.
MOTION_MIN_MEAN = 1.5   # 평균 프레임 차분(0~255)이 이보다 작으면 "움직임 없음"
CONCENTRATION_MIN = 1.3 # 열 분포의 (최댓값/평균) 비. 이보다 평탄하면 "주 피사체 불명확"


def _sample_gray_frames(cap, start: float, end: float) -> list:
    """구간을 균등 분할해 회색조 프레임들을 한 번만 샘플링해 리스트로 반환."""
    import cv2

    duration = max(0.0, end - start)
    if duration <= 0:
        return []

    n = min(MAX_SAMPLES, max(1, int(duration / SAMPLE_INTERVAL)))
    frames = []
    for i in range(n):
        t = start + duration * (i + 0.5) / n
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    return frames


def _column_centroid(col, width: int) -> float | None:
    """열(column) 분포에서 가중 중심 x를 구한다. 너무 평탄하면 None."""
    import numpy as np

    col = np.asarray(col, dtype="float64")
    if col.size == 0:
        return None
    # 1D 스무딩으로 노이즈 완화
    k = max(1, width // 64)
    if k > 1:
        kernel = np.ones(k) / k
        col = np.convolve(col, kernel, mode="same")

    total = col.sum()
    if total <= 0:
        return None
    mean = col.mean()
    if mean <= 0 or (col.max() / mean) < CONCENTRATION_MIN:
        return None  # 주 피사체가 불명확(평탄) → 다음 단계/레터박스로

    xs = np.arange(col.size)
    return float((xs * col).sum() / total)


def _face_center(frames: list, width: int) -> float | None:
    """얼굴 감지 → 면적 가중 median center_x. 없으면 None."""
    import cv2

    cascade_dir = cv2.data.haarcascades
    frontal = cv2.CascadeClassifier(cascade_dir + "haarcascade_frontalface_default.xml")
    profile = cv2.CascadeClassifier(cascade_dir + "haarcascade_profileface.xml")
    if frontal.empty() and profile.empty():
        return None

    centers: list[tuple[float, float]] = []
    for gray in frames:
        faces = list(frontal.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                              minSize=(40, 40)))
        if not profile.empty():
            faces += list(profile.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                                   minSize=(40, 40)))
        for (x, y, w, h) in faces:
            centers.append((x + w / 2.0, float(w * h)))

    if not centers:
        return None

    max_area = max(a for _, a in centers)
    weighted_xs: list[float] = []
    for cx, area in centers:
        weight = max(1, int(round(3 * area / max_area)))  # 1~3
        weighted_xs.extend([cx] * weight)
    return float(median(weighted_xs))


def _motion_center(frames: list, width: int) -> float | None:
    """프레임 차분(움직임)의 열 분포 중심. 움직임이 약하면 None."""
    import cv2
    import numpy as np

    if len(frames) < 2:
        return None

    acc = None
    for a, b in zip(frames, frames[1:]):
        d = cv2.absdiff(a, b).astype("float64")
        acc = d if acc is None else acc + d

    if acc is None or acc.mean() < MOTION_MIN_MEAN * (len(frames) - 1):
        return None

    col = acc.sum(axis=0)
    return _column_centroid(col, width)


def _saliency_center(frames: list, width: int) -> float | None:
    """엣지/디테일 밀집도(Laplacian)의 열 분포 중심. 평탄하면 None."""
    import cv2
    import numpy as np

    acc = None
    for gray in frames:
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        lap = np.abs(cv2.Laplacian(blur, cv2.CV_32F))
        acc = lap if acc is None else acc + lap

    if acc is None:
        return None
    col = acc.sum(axis=0)
    return _column_centroid(col, width)


def _build_params(center_x: float, width: int, height: int) -> dict:
    """center_x를 중심으로 9:16 크롭 창(세로 풀 높이, 가로만 잘라냄)을 구성."""
    cw = min(round(height * TARGET_RATIO), width)
    cx = round(center_x - cw / 2.0)
    cx = max(0, min(cx, width - cw))  # 유효 범위로 clamp
    return {"w": cw, "h": height, "x": cx, "y": 0}


def compute_crop_params(video_path: Path, start: float, end: float) -> dict | None:
    """
    핵심 피사체 중심 크롭 파라미터를 계산한다 (얼굴→움직임→세일런시 순).

    반환:
      {"w": cw, "h": ch, "x": cx, "y": cy}  — crop 필터에 그대로 사용
      None  — 감지 실패/불필요 (호출부가 레터박스 폴백을 사용)
    """
    try:
        import cv2  # noqa: F401
    except Exception:
        return None

    cap = None
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width <= 0 or height <= 0:
            return None

        # 소스가 이미 9:16보다 세로로 길거나 같으면 가로 크롭이 무의미 → 폴백에 맡김
        if width / height <= TARGET_RATIO:
            return None

        frames = _sample_gray_frames(cap, start, end)
        if not frames:
            return None

        # 자동 다단계: 얼굴 → 움직임 → 세일런시
        center_x = _face_center(frames, width)
        if center_x is None:
            center_x = _motion_center(frames, width)
        if center_x is None:
            center_x = _saliency_center(frames, width)
        if center_x is None:
            return None  # 주 피사체 불명확 → 레터박스

        return _build_params(center_x, width, height)
    except Exception:
        return None
    finally:
        if cap is not None:
            cap.release()
