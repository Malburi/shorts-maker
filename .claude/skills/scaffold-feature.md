---
name: scaffold-feature
description: 추출된 프로젝트 컨벤션에 따라 신규 기능을 실제로 스캐폴딩한다. "[기능명] 기능 추가", "새 서비스 만들어줘", "새 파이프라인 노드 추가", "새 창작 단계 추가", "scaffold feature", "패턴대로 만들어줘", "프로젝트 스타일로 새 기능", "컨벤션 따라 보일러플레이트" 요청 시 트리거.
---

# Scaffold Feature (오케스트레이터) — Shorts Maker

`.claude/patterns/`의 추출된 컨벤션을 로드한 뒤 신규 파일을 실제로 생성한다. `scaffolder`(체크리스트)와 달리 파일 생성까지 수행.

## 단계
1. `.claude/patterns/*.md` 모두 로드. 비어 있으면(스켈레톤 상태) `pattern-extractor` 에이전트를 먼저 호출해 본문을 채운다.
2. 사용자에게 기능명·범위 확인 (1~2회 질문): 어느 파이프라인(업로드/창작)인지, 신규 서비스인지 노드인지 엔드포인트인지.
3. 영향받을 레이어 식별:
   - 엔드포인트(`main.py`/`routers/create.py`) → 파이프라인 노드/단계 → 서비스(`services/*.py`) → 모델(`models.py`) → 프론트 컴포넌트.
4. 각 레이어에 컨벤션 준수 보일러플레이트 생성:
   - 서비스: `_xxx_sync()` + `async def xxx()` (`to_thread`), `_client()`/`_run()` 재사용, 모듈 상수 프롬프트, 폴백/timeout 명시.
   - 노드: `node_*`, State 채널 선언, `add_node`/`add_edge` 등록, `_update`.
   - 모델: Pydantic v2.
   - 프론트: SFC + Tailwind + axios/EventSource.
5. 테스트 골격 생성 (`test-generator` — 현재 테스트 전무이므로 새 컨벤션 정립).
6. 사전 영향도 체크: `analyze-impact` 호출로 공유 함수/State/SSE 충돌 여부 확인.

## 주의
- 새 의존성 import 시 `backend/requirements.txt` 동시 갱신 (핵심 발견 1).
- 외부 호출 추가 시 처음부터 폴백/timeout/retry 포함 (핵심 발견 2·3 회귀 방지).

상세 컨벤션은 `.claude/patterns/`, 추출은 harness-ito `pattern-extractor` 참조.
