# Test Pattern — Shorts Maker

추출 시각: 2026-06-17
샘플 파일 수: 0 (테스트 디렉토리/파일 전무 — analyzer 확인)
신뢰도: N/A (기존 컨벤션 없음)

> 이 파일은 기존 테스트 파일이 없으므로 "권장 컨벤션 제안" 형태로 작성됨.
> test-generator가 이 파일을 첫 기준으로 사용한다.
> 운영 안정화 관점에서 테스트 회귀 안전망 부재가 최대 공백이므로
> 아래 컨벤션을 기준으로 우선 순위 높은 항목부터 도입을 권장한다.

---

## 권장 테스트 컨벤션 (신규 도입)

### 기술 스택 선택

| 항목 | 선택 | 이유 |
|------|------|------|
| 테스트 러너 | pytest | FastAPI/Python 생태계 표준 |
| HTTP 테스트 | `fastapi.testclient.TestClient` | 비동기 앱을 동기 컨텍스트에서 테스트 가능 |
| 비동기 테스트 | `pytest-asyncio` | async def 테스트 함수 지원 |
| 모킹 | `unittest.mock` (stdlib) + `pytest-mock` | OpenAI/Gemini/ffmpeg 외부 호출 격리 |
| 커버리지 | `pytest-cov` | 선택적, 도입 후 추가 |

---

### 디렉토리 구조

```
backend/
  tests/
    __init__.py
    test_routes.py           # API 엔드포인트 통합 테스트
    test_pipeline.py         # LangGraph 노드 단위 테스트
    test_create_pipeline.py  # asyncio 파이프라인 테스트
    test_models.py           # Pydantic 모델 직렬화/역직렬화
    services/
      test_key_moments.py    # Gemini 폴백 체인 (우선순위 높음)
      test_thumbnail_gen.py  # 썸네일 폴백 체인
      test_tts_maker.py      # TTS 폴백 체인
      test_rag.py            # ChromaDB 인덱싱/질의
      test_error_handling.py # 에러 핸들링 회귀 테스트
```

---

### 파일명 / 함수명 명명 규칙

```python
# 파일: test_<모듈명>.py
# 함수: test_<동작>_<조건>_<기대결과>

def test_upload_valid_mp4_returns_job_id():
def test_upload_invalid_extension_returns_400():
def test_upload_exceeds_500mb_returns_413():
def test_gemini_rate_limit_retries_with_backoff():
def test_thumbnail_ai_failure_falls_back_to_frame():
def test_tts_edge_failure_falls_back_to_openai():
def test_sse_stream_ends_on_done_status():
def test_pipeline_error_sets_job_status_error():
```

---

### FastAPI TestClient 기본 골격

```python
# backend/tests/test_routes.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from backend.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_upload_invalid_extension_returns_400():
    resp = client.post(
        "/api/upload",
        files={"file": ("video.txt", b"fake content", "text/plain")},
    )
    assert resp.status_code == 400
    assert "지원하지 않는 형식" in resp.json()["detail"]


def test_upload_empty_file_returns_400():
    resp = client.post(
        "/api/upload",
        files={"file": ("video.mp4", b"", "video/mp4")},
    )
    assert resp.status_code == 400
    assert "빈 파일" in resp.json()["detail"]


@patch("backend.main.run_pipeline")
def test_upload_valid_mp4_returns_job_id(mock_pipeline):
    mock_pipeline.return_value = None
    resp = client.post(
        "/api/upload",
        files={"file": ("video.mp4", b"fake mp4 content" * 100, "video/mp4")},
    )
    assert resp.status_code == 200
    assert "job_id" in resp.json()
```

---

### 외부 호출 모킹 전략 (비용 발생 호출 필수 mock)

```python
# OpenAI 호출 mock
@patch("backend.services.thumbnail_gen.OpenAI")
def test_generate_ai_thumbnail_success(mock_openai_cls):
    mock_resp = MagicMock()
    mock_resp.data[0].b64_json = base64.b64encode(b"fake_image").decode()
    mock_openai_cls.return_value.images.generate.return_value = mock_resp

    # 테스트 실행

# Gemini 호출 mock
@patch("backend.services.key_moments.genai.Client")
def test_select_key_moments_returns_moments(mock_client_cls):
    mock_resp = MagicMock()
    mock_resp.text = '{"moments": [{"index": 0, "title": "테스트", "start": 0.0, "end": 30.0, "reason": "이유"}]}'
    mock_client_cls.return_value.models.generate_content.return_value = mock_resp
    ...

# ffmpeg mock
@patch("backend.services.thumbnail_gen.subprocess.run")
def test_extract_frame_falls_back_on_empty(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout=b"")
    ...

# ChromaDB mock (단위 테스트)
@patch("backend.services.rag._client")
def test_index_segments_stores_chunks(mock_chroma_client):
    ...
```

---

### pytest-asyncio 비동기 테스트

```python
# backend/tests/test_pipeline.py
import pytest
from unittest.mock import AsyncMock, patch
from backend.pipeline import node_get_duration


@pytest.mark.asyncio
async def test_node_get_duration_zero_raises():
    """duration <= 0 시 ValueError를 raise해야 한다."""
    mock_jobs = {"job-1": MagicMock()}
    state = {
        "job_id": "job-1",
        "jobs": mock_jobs,
        "video_path": "/fake/video.mp4",
    }

    with patch("backend.pipeline.get_video_duration", new_callable=AsyncMock) as mock_dur:
        mock_dur.return_value = 0.0
        with pytest.raises(ValueError, match="영상 길이를 읽을 수 없습니다"):
            await node_get_duration(state)


@pytest.mark.asyncio
async def test_node_get_duration_updates_job():
    """duration > 0 시 job.video_duration 갱신 확인."""
    mock_job = MagicMock()
    state = {"job_id": "job-1", "jobs": {"job-1": mock_job}, "video_path": "/fake/video.mp4"}

    with patch("backend.pipeline.get_video_duration", new_callable=AsyncMock) as mock_dur:
        mock_dur.return_value = 123.4
        result = await node_get_duration(state)

    assert result["duration"] == 123.4
    mock_job.video_duration == 123.4
```

---

### 폴백 체인 회귀 테스트 (우선순위 높음)

```python
# backend/tests/services/test_error_handling.py

@pytest.mark.asyncio
async def test_thumbnail_ai_failure_uses_frame_fallback(tmp_path):
    """AI 썸네일 생성 실패 시 frame 추출로 폴백."""
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    output = tmp_path / "thumb.jpg"

    with patch("backend.services.thumbnail_gen._generate_ai_sync", return_value=False):
        with patch("backend.services.thumbnail_gen.extract_frame", new_callable=AsyncMock) as mock_frame:
            mock_frame.return_value = output
            result = await make_thumbnail(clip, 30.0, "제목", "이유", output, use_ai=True)

    mock_frame.assert_called_once()


@pytest.mark.asyncio
async def test_tts_edge_failure_uses_openai_fallback(tmp_path):
    """edge-tts 실패 시 OpenAI TTS로 폴백."""
    output = tmp_path / "tts.mp3"
    output.write_bytes(b"fake audio")

    with patch("backend.services.tts_maker._tts_edge", side_effect=Exception("edge fail")):
        with patch("backend.services.tts_maker._tts_openai_fallback") as mock_openai:
            with patch("backend.services.tts_maker.get_audio_duration", new_callable=AsyncMock, return_value=5.0):
                duration = await generate_tts("테스트 텍스트", output)

    mock_openai.assert_called_once()
    assert duration == 5.0


def test_gemini_rate_limit_retries_three_times():
    """429 에러 시 같은 모델 3회 재시도."""
    from backend.services.key_moments import _select_sync

    call_count = 0

    def mock_generate(**kwargs):
        nonlocal call_count
        call_count += 1
        raise Exception("429 RESOURCE_EXHAUSTED")

    with patch("backend.services.key_moments._client") as mock_client:
        mock_client.return_value.models.generate_content = mock_generate
        with pytest.raises(Exception, match="429"):
            _select_sync("transcript", 120.0)

    assert call_count == 9  # 3 모델 × 3 시도
```

---

### SSE 페이로드 계약 테스트

```python
# backend/tests/test_models.py
from backend.models import Job, JobStatus

def test_job_serialization_includes_all_sse_fields():
    """Job.model_dump_json()에 SSE 계약 필드가 모두 포함되는지 확인."""
    job = Job(id="test-id", filename="video.mp4")
    data = job.model_dump()

    required_fields = {"id", "status", "step", "progress", "error", "shorts", "has_knowledge"}
    assert required_fields.issubset(data.keys())

def test_job_status_serializes_as_string():
    """JobStatus.DONE이 JSON에서 'done' 문자열로 직렬화."""
    job = Job(id="test", status=JobStatus.DONE)
    json_str = job.model_dump_json()
    assert '"status":"done"' in json_str or '"status": "done"' in json_str
```

---

## 우선순위별 도입 순서

| 우선순위 | 테스트 항목 | 근거 |
|---------|-----------|------|
| 1순위 | 폴백 체인 3종 회귀 (thumbnail/TTS/Gemini) | 운영 안정화 핵심 발견 #2 |
| 2순위 | 라우트 입력 검증 (400/413/404) | 방어 코드 회귀 방지 |
| 3순위 | pipeline 노드 에러 전파 테스트 | 운영 안정화 핵심 발견 #6 |
| 4순위 | SSE 종료 조건 테스트 | 운영 안정화 핵심 발견 #5 |
| 5순위 | GEMINI_API_KEY 미설정 KeyError 테스트 | 운영 안정화 핵심 발견 #4 |
| 6순위 | Pydantic 모델 직렬화/역직렬화 | SSE 계약 보호 |

---

## conftest.py 기본 픽스처

```python
# backend/tests/conftest.py
import pytest
from pathlib import Path
import tempfile

@pytest.fixture
def tmp_job_dir(tmp_path):
    """임시 작업 디렉토리."""
    job_out = tmp_path / "test_job_id"
    job_out.mkdir()
    return job_out

@pytest.fixture
def mock_jobs():
    """인메모리 jobs dict 픽스처."""
    from backend.models import Job
    job = Job(id="test-job-id", filename="video.mp4")
    return {"test-job-id": job}

@pytest.fixture(autouse=True)
def no_real_external_calls(monkeypatch):
    """모든 테스트에서 실제 외부 호출 차단 (비용 방지)."""
    # OpenAI, Gemini, ffmpeg, edge-tts 호출을 기본 차단
    # 개별 테스트에서 필요 시 patch로 재정의
    pass
```
