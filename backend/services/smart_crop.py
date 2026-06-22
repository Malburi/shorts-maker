"""
스마트 크롭: 가로 영상을 9:16 세로로 변환할 때 핵심 피사체를 감지해
크롭 창을 그 쪽으로 이동시킨다. 장르를 가리지 않도록 자동 다단계로 동작한다.

감지 우선순위 (앞 단계가 신호를 못 내면 다음 단계로):
  1) 얼굴   — OpenCV Haar cascade (정면+측면). 인물/토킹헤드.
  2) 움직임 — 프레임 차분의 열(column) 분포. 스포츠 공·게임 캐릭터·액션 등
              "움직이는 주 피사체"를 클래스 무관하게 추적.
  3) 세일런시 — 엣지/디테일 밀집도(Laplacian)의 열 분포. 정지 장면의 주 피사체.
  4) 모두 실패 → None → 호출부가 레터박스(풀샷 + 위아래 검은 여백) 폴백.

각 단계는 가로 1D "중요도 프로파일"을 만들고, 공통 로직(_best_window_center)이
그 위에서 **9:16 크롭 창이 담을 수 있는 중요도 합이 최대가 되는 위치**를 찾는다.
방송 화면의 수어 통역사 박스·로고벽 오탐처럼 한쪽에 몰린 부차적 신호가 있어도
"가장 큰 단일 군집"을 고르므로 평균/중앙값이 두 군집 사이로 끌려가지 않는다.

opencv-python(+numpy)만 사용하므로 별도 모델 다운로드/무거운 의존성이 없다.
import/감지 실패는 모두 None으로 흡수해 파이프라인이 죽지 않도록 한다.
"""
from pathlib import Path

TARGET_W = 1080
TARGET_H = 1920
TARGET_RATIO = TARGET_W / TARGET_H  # 9:16 = 0.5625

# 샘플링 설정
SAMPLE_INTERVAL = 0.5   # 초 간격으로 프레임 샘플링
MAX_SAMPLES = 20        # 클립당 최대 샘플 수 (처리 시간 가드)

# 움직임/세일런시 임계값
MOTION_MIN_MEAN = 1.5       # 프레임당 평균 차분(0~255)이 이보다 작으면 "움직임 없음"
# 최적 창/최악 창 중요도 비. 이보다 평탄하면(=주 피사체 불명확) 다음 단계/레터박스로.
WINDOW_CONCENTRATION_MIN = 1.2


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


def _best_window_center(prof, width: int, cw: int, check_concentration: bool) -> float | None:
    """
    1D 중요도 프로파일 위에서 폭 cw 창의 합이 최대인 위치를 찾아,
    그 창 내부의 무게중심 x를 반환한다.

    check_concentration=True면 최적/평균 창 합의 비가 임계값 미만일 때
    (=신호가 평탄해 주 피사체 불명확) None을 반환한다. 얼굴 단계는 검출 자체가
    강한 신호이므로 False로 호출한다.
    """
    import numpy as np

    prof = np.asarray(prof, dtype="float64")
    if prof.size == 0 or prof.sum() <= 0:
        return None

    cw = min(cw, width)
    if cw >= width:
        xs = np.arange(prof.size)
        return float((xs * prof).sum() / prof.sum())

    csum = np.concatenate([[0.0], np.cumsum(prof)])
    starts = np.arange(0, width - cw + 1)
    wsum = csum[starts + cw] - csum[starts]

    if check_concentration:
        mean = wsum.mean()
        if mean <= 0 or (wsum.max() / mean) < WINDOW_CONCENTRATION_MIN:
            return None

    best = int(starts[int(np.argmax(wsum))])
    seg = prof[best:best + cw]
    seg_total = seg.sum()
    if seg_total <= 0:
        return best + cw / 2.0
    xs = np.arange(best, best + cw)
    return float((xs * seg).sum() / seg_total)


# 주 피사체 얼굴 대비 이 비율 미만 점수의 얼굴은 2차 인물/오탐으로 보고 제외.
FACE_DOMINANT_RATIO = 0.45
# 얼굴 중앙 선호 강도. 화면 가장자리 얼굴의 가중치를 (1-이 값)까지 낮춰,
# 방송에서 흔한 가장자리 2차 인물보다 중앙의 주 피사체를 우선한다. 0이면 비활성.
FACE_CENTRALITY_STRENGTH = 0.5


def _face_profile(frames: list, width: int):
    """얼굴 감지 → 면적×선명도 가중 중요도 프로파일(길이 width). 얼굴 없으면 None.

    각 얼굴의 점수 = 면적 × 선명도(라플라시안 분산). 카메라에 가까운 주 피사체는
    크고 선명한 반면, 배경의 2차 인물(아웃포커스)·수어 통역사 박스·로고벽 오탐은
    작거나 흐릿해 점수가 낮다. 최고 점수의 FACE_DOMINANT_RATIO 미만 얼굴은 버린 뒤,
    남은 얼굴 점수를 각자의 가로 구간[x, x+w]에 고르게 분배한다.
    """
    import cv2
    import numpy as np

    cascade_dir = cv2.data.haarcascades
    frontal = cv2.CascadeClassifier(cascade_dir + "haarcascade_frontalface_default.xml")
    profile = cv2.CascadeClassifier(cascade_dir + "haarcascade_profileface.xml")
    if frontal.empty() and profile.empty():
        return None

    # 1패스: 모든 얼굴 수집 (가로 구간 + 점수=면적×선명도)
    dets = []  # (x0, x1, score)
    for gray in frames:
        faces = list(frontal.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6,
                                              minSize=(40, 40)))
        if not profile.empty():
            faces += list(profile.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6,
                                                   minSize=(40, 40)))
        for (x, y, w, h) in faces:
            x0 = max(0, x)
            x1 = min(width, x + w)
            y0 = max(0, y)
            y1 = min(gray.shape[0], y + h)
            if x1 <= x0 or y1 <= y0:
                continue
            roi = gray[y0:y1, x0:x1]
            # 선명도 = 라플라시안 분산. 흐린 배경 인물은 낮음. +1로 0 방지.
            sharp = float(cv2.Laplacian(roi, cv2.CV_32F).var()) + 1.0
            # 중앙 선호: 가장자리 얼굴 가중치 하향 (가장자리→1-STRENGTH, 중앙→1.0)
            cx = (x0 + x1) / 2.0
            centrality = 1.0 - FACE_CENTRALITY_STRENGTH * min(1.0, abs(cx - width / 2.0) / (width / 2.0))
            score = float(w * h) * sharp * centrality
            dets.append((x0, x1, score))

    if not dets:
        return None

    # 주 피사체(최고 점수)의 일정 비율 미만은 제외
    max_score = max(s for _, _, s in dets)
    threshold = FACE_DOMINANT_RATIO * max_score

    prof = np.zeros(width, dtype="float64")
    for x0, x1, score in dets:
        if score < threshold:
            continue
        prof[x0:x1] += score / (x1 - x0)

    return prof if prof.sum() > 0 else None


def _motion_profile(frames: list, width: int):
    """프레임 차분(움직임)의 열 분포 프로파일. 움직임이 약하면 None."""
    import cv2

    if len(frames) < 2:
        return None

    acc = None
    for a, b in zip(frames, frames[1:]):
        d = cv2.absdiff(a, b).astype("float64")
        acc = d if acc is None else acc + d

    if acc is None or acc.mean() < MOTION_MIN_MEAN * (len(frames) - 1):
        return None
    return acc.sum(axis=0)


def _saliency_profile(frames: list, width: int):
    """엣지/디테일 밀집도(Laplacian)의 열 분포 프로파일."""
    import cv2
    import numpy as np

    acc = None
    for gray in frames:
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        lap = np.abs(cv2.Laplacian(blur, cv2.CV_32F))
        acc = lap if acc is None else acc + lap

    if acc is None:
        return None
    return acc.sum(axis=0)


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

        cw = min(round(height * TARGET_RATIO), width)

        # 자동 다단계: 얼굴 → 움직임 → 세일런시.
        # 얼굴은 검출 자체가 강한 신호 → 집중도 검사 생략. 움직임/세일런시는 검사.
        center_x = None
        face = _face_profile(frames, width)
        if face is not None:
            center_x = _best_window_center(face, width, cw, check_concentration=False)
        if center_x is None:
            motion = _motion_profile(frames, width)
            if motion is not None:
                center_x = _best_window_center(motion, width, cw, check_concentration=True)
        if center_x is None:
            sal = _saliency_profile(frames, width)
            if sal is not None:
                center_x = _best_window_center(sal, width, cw, check_concentration=True)
        if center_x is None:
            return None  # 주 피사체 불명확 → 레터박스

        return _build_params(center_x, width, height)
    except Exception:
        return None
    finally:
        if cap is not None:
            cap.release()
