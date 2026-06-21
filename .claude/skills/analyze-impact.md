---
name: analyze-impact
description: 변경 대상(파일/함수/파이프라인 노드/서비스/엔드포인트)의 직간접 영향과 위험도를 분석한다. "이거 수정하면 어디 영향?", "영향도 분석", "impact analysis", "이 함수 수정해도 돼?", "concat_shorts 바꾸면 어디 영향?", "이 노드 수정 영향", "어디서 쓰이고 있어?", "이 메서드 호출처", "이거 건드려도 돼?" 요청 시 트리거.
---

# Analyze Impact (오케스트레이터) — Shorts Maker

변경 대상이 주어지면 `impact-analyzer` 에이전트를 호출해 직간접 영향과 위험도를 평가한다.

## 입력
사용자가 자연어로 변경 대상 명시 (예: "caption_maker._write_ass 시그니처 변경 예정", "key_moments 폴백 추가").

## 실행
1. `_workspace/index/` 인덱스 존재 확인 (call_graph.json, data_flow.json, external_io.json, symbols.json). 없으면 → analyzer를 `feature-scoped` 모드로 호출해 최소 인덱스 생성.
2. `impact-analyzer` 에이전트 호출:
   - 입력: 변경 대상 + 인덱스 경로
   - 출력: `_workspace/impact_<slug>.md`
3. 결과 보고: 위험도(1~10), 영향받는 파일/노드/서비스, 외부 시스템(LLM/ffmpeg/ChromaDB), 영향받는 테스트(현재 없음 → 신규 권고).

## 이 프로젝트 특이 영향 포인트 (impact-analyzer에 반드시 전달)
- **두 파이프라인 공유 함수**: `shorts_maker.concat_shorts`, `thumbnail_gen.extract_frame`, `caption_maker._write_ass`/`_burn` 변경은 업로드+창작 양쪽 동시 영향.
- **캡슐화 경계 침범**: `create_pipeline.py`가 `caption_maker`의 비공개 함수를 직접 import. 비공개 함수 시그니처 변경 시 양쪽 동시 영향.
- **LangGraph State 채널**: `PipelineState` 채널 추가/변경은 모든 `node_*`와 Send fan-out 병합에 영향. `operator.add` 누적 채널 주의.
- **SSE 계약**: jobs/create_jobs dict 필드명 변경은 `/events` SSE 페이로드 → 프론트 `App.vue`/`AICreateTab.vue` 파싱에 직접 영향.
- **외부 호출 변경**: timeout/retry/폴백 추가/제거는 운영 안정성에 직결 — `external_io.json`의 라인별 현황과 대조.

상세 로직은 harness-ito `impact-analyzer` 에이전트 참조.
