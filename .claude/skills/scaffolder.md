---
name: scaffolder
description: 신규 파일/모듈 추가 시 따라야 할 기본 체크리스트를 제공한다. "새 서비스 추가", "새 엔드포인트 만들기", "새 파이프라인 노드", "새 Vue 컴포넌트", "신규 파일 체크리스트", "scaffold", "보일러플레이트" 요청 시 트리거. 실제 파일 생성(컨벤션 강제)은 scaffold-feature가 담당.
---

# Scaffolder — Shorts Maker 신규 파일 체크리스트

> 이 스킬은 *체크리스트만* 제공한다. 추출된 컨벤션대로 실제 파일을 생성하려면 `scaffold-feature`를 사용한다.

## 신규 서비스 (`backend/services/<name>.py`)
- [ ] blocking IO는 `def _<name>_sync(...)` 동기 구현 + `async def <name>(...)`가 `asyncio.to_thread(_<name>_sync, ...)` 래핑 (프로젝트 일관 패턴).
- [ ] OpenAI 호출 시 `_client()` 헬퍼 (단, 운영 안정화 권고: `timeout`/`max_retries` 설정 고려).
- [ ] subprocess는 기존 `_run(cmd)` 패턴 (`capture_output=True`) 재사용.
- [ ] LLM 프롬프트는 모듈 상단 상수(`*_SYSTEM_PROMPT`)로, JSON 강제 응답.
- [ ] 외부 호출이면 폴백/timeout/retry 정책 명시 (analyzer 핵심 발견 2·3 참조).
- [ ] 에러는 한국어 메시지 + `f"{type(e).__name__}: {e}"` 포맷.

## 신규 엔드포인트
- [ ] 업로드 계열 → `backend/main.py`, 창작 계열 → `backend/routers/create.py`.
- [ ] 입력 검증(확장자/크기/정규식) 추가 — 기존 upload/youtube/delete 패턴 참조.
- [ ] 응답 모델은 `backend/models.py`에 Pydantic v2로 정의.
- [ ] 장시간 작업이면 `BackgroundTasks` + jobs/create_jobs dict + SSE `/events`.

## 신규 파이프라인 노드 (업로드)
- [ ] `backend/pipeline.py`에 `def node_<name>(state: PipelineState)` 정의.
- [ ] 누적 채널이면 `Annotated[list, operator.add]` 사용.
- [ ] StateGraph에 `add_node` + `add_edge`/`add_conditional_edges` 등록.
- [ ] `_update(jobs, job_id, ...)`로 진행률 갱신.
- [ ] State 채널을 모두 선언 (analyzer 주의: 미선언 채널 데드 코드 사례 있음).

## 신규 Vue 컴포넌트 (`frontend/src/components/<Name>.vue`)
- [ ] SFC (`<template>/<script setup>/<style>`), Tailwind 클래스.
- [ ] API는 axios (ChatPanel만 fetch), 경로는 vite proxy `/api`.
- [ ] SSE면 EventSource — `onerror` 시 재연결 고려 (analyzer 핵심 발견 5: 현재 재연결 없음).

## 공통
- [ ] 테스트 디렉토리가 없으므로 신규 코드에 테스트 골격 동반 권장 (`test-generator` 활용).
- [ ] 새 의존성 import 시 `backend/requirements.txt` 갱신 (핵심 발견 1: 누락 다수).
