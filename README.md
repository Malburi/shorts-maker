# Shorts Maker

영상을 업로드하면 AI가 핵심 장면을 추출하여 쇼츠 클립과 썸네일을 자동 생성합니다.

## 처리 흐름

```
영상 업로드
  → ffmpeg 오디오 추출
  → OpenAI Whisper 전사 (타임스탬프)
  → GPT-4o-mini 핵심 장면 3~5개 선정
  → ffmpeg 9:16 쇼츠 클립 생성 (병렬)
  → GPT-image-1 썸네일 생성 (병렬)
  → 결과 갤러리 표시
```

## 사전 요구사항

- Python 3.11+
- Node.js 18+
- `ffmpeg` (PATH에 등록)
- `OPENAI_API_KEY` 환경변수

## 설치

```powershell
# 백엔드
cd backend
pip install -r requirements.txt

# 프론트엔드
cd frontend
npm install
```

## 실행

```powershell
# 방법 1: 통합 스크립트
.\start.ps1

# 방법 2: 수동
# 터미널 1 - 백엔드
cd backend
uvicorn main:app --reload

# 터미널 2 - 프론트엔드
cd frontend
npm run dev
```

브라우저에서 http://localhost:5173 접속

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/upload` | 영상 업로드 → job_id 반환 |
| GET | `/api/jobs/{id}` | 작업 상태 조회 |
| GET | `/api/jobs/{id}/events` | SSE 실시간 진행 스트림 |
| GET | `/outputs/{id}/short_N.mp4` | 생성된 쇼츠 |
| GET | `/outputs/{id}/thumb_N.jpg` | 생성된 썸네일 |

## 비용 주의

- Whisper: ~$0.006/분
- GPT-4o-mini: 매우 저렴
- GPT-image-1 (low): 약 $0.011/장
- AI 썸네일 끄기: 업로드 화면에서 체크박스 해제 → 프레임 추출로 대체
