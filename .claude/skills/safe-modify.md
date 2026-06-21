---
name: safe-modify
description: 코드 변경을 사전 영향 분석 → 적용 → 사후 안전성 평가 순으로 안전하게 수행한다. "이거 안전하게 수정해줘", "회귀 위험 없이 변경", "safe modify", "이 변경 안전한가?", "변경 전 체크", "이 패치 적용해도 돼?", "GO/NO-GO 판단", "변경 리뷰" 요청 시 트리거.
---

# Safe Modify (오케스트레이터) — Shorts Maker

테스트 안전망이 전무한 프로젝트이므로, 변경 전후 영향·안전성 평가를 자동 수행한다.

## 단계
1. **사전 분석** — `analyze-impact` 호출. 두 파이프라인 공유 함수·State 채널·SSE 계약·외부 호출 변경 여부를 먼저 확인.
2. **변경 적용** — 사용자 확인 후 코드 수정. 프로젝트 컨벤션(`_xxx_sync`+`to_thread`, `_update`, 한국어 에러 메시지, JSON 강제 프롬프트) 준수.
3. **사후 검증** — `change-safety` 에이전트 호출:
   - 입력: git diff + impact 리포트
   - 출력: `_workspace/safety_<slug>.md` (GO/HOLD/STOP 권고)
4. **테스트 권고** — 테스트 디렉토리가 없으므로 `test-generator`로 회귀 테스트 골격 생성 위치 제안.

## 이 프로젝트에서 STOP/HOLD 가중치가 높은 변경
- 공유 함수(`concat_shorts`, `extract_frame`, `_write_ass`, `_burn`) 시그니처 변경 → 양쪽 파이프라인 동시 영향, HOLD 기본.
- `PipelineState` 채널 구조 변경 → 전 노드 영향.
- SSE 페이로드 필드명/구조 변경 → 프론트 동시 수정 필요.
- 외부 호출의 timeout/retry/폴백 **제거** → 운영 안정성 회귀 (반대로 추가는 안정화 개선).
- `requirements.txt` 의존성 추가 시 실제 설치/버전 고정 동반 확인.

## 운영 안정화 개선 변경 (장려)
- create_pipeline 이미지 폴백 추가, OpenAI timeout/retry 도입, GEMINI_API_KEY os.getenv 전환, SSE heartbeat/재연결, 노드별 에러 핸들링 — 이들은 안전성 평가에서 가산.

상세 로직은 harness-ito `change-safety` 에이전트 참조.
