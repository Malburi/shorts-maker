# ito-guide — shorts-maker 하네스 사용 설명서

이 문서는 `harness-ito`로 생성된 shorts-maker 전용 하네스(스킬·에이전트·패턴·인덱스)를 **언제, 어떻게** 쓰는지 안내한다. 대상 프로젝트는 FastAPI + LangGraph 업로드 파이프라인, asyncio 기반 AI Create 파이프라인, Vue3/Vite 프론트, SSE 진행률, 외부 LLM(OpenAI/Gemini) 및 ffmpeg를 사용하는 AI 유튜브 쇼츠 생성기다.

생성된 자산 한눈에 보기:

| 종류 | 파일 |
|------|------|
| 스킬 | `trace`, `find-logic`, `scaffolder`, `analyze-impact`, `safe-modify`, `scaffold-feature` |
| 에이전트 | `domain-expert` (+ harness-ito 공용: `legacy-decoder`, `doc-syncer` 등) |
| 패턴 | `route`, `pipeline_node`, `service`, `model`, `error_handling`, `sse`, `component`, `test` (스켈레톤 — 본문은 pattern-extractor가 채움) |
| 인덱스 | `_workspace/index/*.json` (call_graph / data_flow / external_io / env_branches / dead_code / symbols) |

---

## 1. 스킬 사용법

각 스킬은 자연어 트리거로 자동 발동된다. 아래는 실제 생성된 스킬 6종이다.

### `trace` — 요청/처리 흐름 추적
진입점(FastAPI 라우트)부터 외부 호출(ffmpeg/LLM/ChromaDB)까지 단계별로 따라간다. **두 파이프라인(업로드 vs AI Create)을 먼저 판별**한 뒤 추적한다.
> 트리거 예: "업로드하면 뭐가 실행돼?" · "AI 창작 파이프라인 따라가줘" · "SSE 진행률이 어떻게 전달돼?"

### `find-logic` — 역방향 코드 탐색
기능명·키워드·엔드포인트로 담당 파일·함수·노드를 찾는다. `symbols.json` 인덱스를 먼저 쓰고 없으면 grep으로 보완한다.
> 트리거 예: "자막 번인 코드 찾아줘" · "TTS 폴백 어디 있어?" · "핵심 장면 선택 로직 어디?"

### `scaffolder` — 신규 파일 체크리스트
새 서비스/엔드포인트/노드/Vue 컴포넌트를 추가할 때 따라야 할 컨벤션 **체크리스트만** 제공한다(파일 생성 안 함).
> 트리거 예: "새 서비스 추가 체크리스트" · "새 파이프라인 노드 만들 때 뭐 챙겨?" · "신규 파일 보일러플레이트"

### `analyze-impact` — 영향도 분석 (오케스트레이터)
변경 대상의 직간접 영향과 위험도를 `impact-analyzer` 에이전트로 평가한다. 두 파이프라인 공유 함수·State 채널·SSE 계약·외부 호출 변경을 중점 점검.
> 트리거 예: "concat_shorts 바꾸면 어디 영향?" · "이 노드 수정해도 돼?" · "어디서 쓰이고 있어?"

### `safe-modify` — 안전 변경 (오케스트레이터)
사전 영향 분석 → 변경 적용 → 사후 `change-safety` 평가(GO/HOLD/STOP) 순으로 수행한다. 테스트 안전망이 전무하므로 변경 전후를 자동 검증한다.
> 트리거 예: "이거 안전하게 수정해줘" · "이 변경 안전한가?" · "GO/NO-GO 판단해줘"

### `scaffold-feature` — 컨벤션대로 실제 스캐폴딩 (오케스트레이터)
`.claude/patterns/`의 추출된 컨벤션을 로드해 신규 기능 파일을 **실제로 생성**한다. `scaffolder`(체크리스트)와 달리 코드까지 만든다.
> 트리거 예: "자막 스타일 선택 기능 추가" · "프로젝트 스타일로 새 창작 단계 만들어줘" · "패턴대로 새 서비스 만들어줘"

---

## 2. 에이전트 직접 호출

스킬을 거치지 않고 에이전트를 직접 부를 수 있다.

- **`domain-expert`** — 이 프로젝트 도메인 전문가. 아키텍처·요청 흐름·컨벤션·외부 통신·운영 안정화 핵심 발견 7건을 모두 숙지한 상태로 답한다. "이 프로젝트 어떻게 동작해?", "왜 이렇게 설계됐어?", "운영 위험 뭐가 있어?" 같은 **전반 이해 질문**에 가장 적합. 읽기/탐색 도구(Read/Grep/Glob/Bash)로 제한되어 코드를 변경하지 않는다.
- **`legacy-decoder`** (harness-ito 공용) — 주석 없는·암묵 컨벤션 코드를 사람이 읽을 수 있게 역공학한다. "이 함수 뭐하는 거야?", "이 ffmpeg 인자 조합 해석해줘"처럼 **난해한 코드 블록 해독**에 사용. 결과는 `_workspace/decoded_<slug>.md`.
- **`doc-syncer`** (harness-ito 공용) — 코드 변경 후 `CLAUDE.md`/README/변경 이력 등 문서 일관성을 점검·갱신한다. "변경 사항 문서 동기화", "CLAUDE.md 업데이트" 시 호출. `safe-modify` 이후 이어 부르면 좋다.

> 호출 방법: 자연어로 위 트리거 문장을 말하면 자동 선택된다. 명시적으로 부르려면 "domain-expert 에이전트로 …"처럼 지정한다.

---

## 3. 패턴 파일 참조

`.claude/patterns/*.md`는 레이어별 코드 컨벤션을 담는다. 현재는 **스켈레톤(추출 대상만 명시)** 상태이며 본문은 `pattern-extractor` 에이전트가 채운다("패턴 추출해줘"). 이 프로젝트는 전통적 Controller/Service/DAO 구조가 아니라 **Route → Pipeline → Service → Model** 구조라 그에 맞춰 명명되어 있다.

| 패턴 파일 | 용도 | 추출 샘플 |
|-----------|------|-----------|
| `route_pattern.md` | 라우트 데코레이터·입력 검증·BackgroundTasks 기동·SSE 엔드포인트 | `main.py`, `routers/create.py` |
| `pipeline_node_pattern.md` | LangGraph `node_*` 정의·State 채널·add_edge/Send 등록·`_update` | `pipeline.py` |
| `service_pattern.md` | `_xxx_sync()` + `async def`(to_thread) 래핑·`_client()`/`_run()` 재사용·모듈 상수 프롬프트 | `services/*.py` |
| `model_pattern.md` | Pydantic v2 + Enum 스키마 | `models.py` |
| `error_handling_pattern.md` | 예외 처리·재시도/백오프·폴백 체인 + **안티패턴(개선 방향)** | `pipeline.py`, `create_pipeline.py`, `key_moments.py`, `main.py` |
| `sse_pattern.md` | StreamingResponse·폴링 간격·EventSource 재연결 (운영 안정화 영역) | `main.py`, `App.vue`, `AICreateTab.vue` |
| `component_pattern.md` | Vue3 SFC + Tailwind + axios/EventSource (Modern SPA) | `frontend/src/components/*.vue` |
| `test_pattern.md` | 테스트 컨벤션 정립용 (현재 테스트 전무) | — |

**scaffold-feature와의 연계**: `scaffold-feature`는 1단계에서 이 패턴 파일들을 모두 로드한다. 비어 있으면(스켈레톤) 먼저 `pattern-extractor`를 호출해 본문을 채운 뒤 그 컨벤션대로 보일러플레이트를 생성한다. 즉 **패턴 본문이 채워져 있어야 scaffold-feature가 정확한 코드를 만든다.** 신규 기능 작업 전 한 번 "패턴 추출해줘"를 실행해 두면 좋다.

---

## 4. 인덱스 파일 설명

`_workspace/index/*.json`은 정적 분석으로 추출한 코드 지도다. `analyze-impact`/`find-logic`/`trace`가 이 인덱스를 우선 활용하고, 부족하면 grep으로 보완한다. **코드 수정 전 영향 확인은 아래 순서로** 한다.

| 인덱스 파일 | 용도 | 코드 수정 전 확인 포인트 |
|-------------|------|--------------------------|
| `symbols.json` | 파일별 함수·클래스·노드·모델 + 라인 | "이 함수 어디 정의됐나" 빠른 위치 확인 |
| `call_graph.json` | 정적 호출 그래프 (import/호출 + LangGraph 토폴로지) | **수정 대상의 호출처(in-degree) 확인** — 공유 함수면 양쪽 파이프라인 영향 |
| `data_flow.json` | PipelineState 상태 흐름 + 비동기 경계(Send/gather) | State 채널·jobs dict 변경이 어디로 흐르는지 |
| `external_io.json` | 외부 호출(LLM/ffmpeg/ChromaDB)별 폴백/재시도/timeout 유무 라인별 기록 | 외부 호출 변경 시 폴백/timeout 회귀 여부 |
| `env_branches.json` | 환경변수 의존·분기 (GEMINI_API_KEY 등) | env 관련 수정 영향 |
| `dead_code.json` | 미사용 함수/import/엔드포인트 후보 (자동 제거 권고 아님) | 제거 전 동적 디스패치 가능성 점검 |

**영향 확인 권장 흐름**: 수정 대상 함수를 `call_graph.json`에서 in-degree 조회 → 공유 함수(`concat_shorts`, `extract_frame`, `_write_ass`, `_burn`)면 두 파이프라인 동시 영향 → 외부 호출 관련이면 `external_io.json` 대조 → 그 다음 `analyze-impact` 스킬로 종합 위험도 산출.

---

## 5. 실전 시나리오

### 시나리오 A — 신규 AI 서비스 / 파이프라인 노드 추가
새 외부 LLM 호출 서비스나 업로드 파이프라인 노드를 붙일 때.
- **순서**: `scaffolder`(체크리스트로 챙길 것 파악) → "패턴 추출해줘"(패턴 본문 미충전 시) → `scaffold-feature`(실제 생성) → `analyze-impact`(공유 함수/State/SSE 충돌 확인).
- **주의**: 새 import는 `backend/requirements.txt` 동시 갱신, 외부 호출은 **처음부터 폴백/timeout/retry 포함**.
> 트리거 예: "효과음 삽입 서비스 추가" · "전사 후 키워드 태깅 노드 추가해줘 컨벤션 따라"

### 시나리오 B — 기존 노드/공유 함수 수정 전 영향 확인
`concat_shorts` 같은 두 파이프라인 공유 함수나 `PipelineState` 채널을 건드리기 전.
- **순서**: `analyze-impact`(위험도 + 영향 범위) → 필요 시 바로 `safe-modify`로 변경+사후 평가.
- **핵심**: 공유 함수 시그니처 변경은 HOLD 기본, SSE 페이로드 필드 변경은 프론트 동시 수정 필요.
> 트리거 예: "caption_maker._write_ass 시그니처 바꾸려는데 어디 영향?" · "이 노드 수정해도 돼?"

### 시나리오 C — SSE / 창작 파이프라인 오류 추적
진행률이 멈추거나 AI Create가 ERROR로 끝날 때.
- **순서**: `trace`(어느 파이프라인·어느 단계인지 흐름 추적) → `external_io.json`으로 해당 외부 호출의 폴백/timeout 유무 확인 → 필요 시 `domain-expert`에게 운영 위험 맥락 질의.
- **핵심 단서**: create_pipeline 이미지 생성 폴백 부재(한 장면 실패=전체 ERROR), OpenAI timeout/retry 부재(SSE 무한 대기), SSE 재연결 부재(서버 jobs dict 소실 시 조용히 break).
> 트리거 예: "AI 창작이 자꾸 ERROR로 끝나는데 어디서 막혀?" · "SSE 진행률이 어떻게 전달돼?"

### 시나리오 D — 폴백 체인 보강 (운영 안정화)
이미지 생성 폴백 추가, OpenAI timeout/retry 도입, GEMINI_API_KEY os.getenv 전환 등.
- **순서**: `safe-modify`로 진행(이런 안정화 변경은 안전성 평가에서 **가산점**) → 변경 후 `test-generator`로 회귀 테스트 골격, `doc-syncer`로 문서 동기화.
- **참고**: 정상 폴백 3종(썸네일 gpt-image-1→frame, TTS edge→OpenAI, 핵심장면 Gemini 3모델→시간균등분할)을 본보기로 삼는다.
> 트리거 예: "create_pipeline 이미지 생성에 프레임 폴백 추가해줘 안전하게" · "OpenAI 호출에 timeout/retry 넣어줘"

---

## 6. 주의사항 (CLAUDE.md 핵심 요약)

1. **requirements.txt 누락 의존성** — `langgraph`/`langchain`/`google-genai`/`chromadb`/`ddgs`가 코드에서 import되나 명세에 없을 수 있다. 새 import 시 반드시 동시 갱신(배포 치명, 최우선).
2. **폴백 체인 비대칭** — create_pipeline 이미지 생성에는 폴백이 없어 asyncio.gather fail-fast로 한 장면 실패가 전체 ERROR로 전파된다.
3. **OpenAI timeout/retry 전무** — Whisper/gpt-4o/embeddings/이미지가 무제한 대기 가능 → SSE 폴링이 행에 걸린다.
4. **두 파이프라인 공유 함수 + 캡슐화 침범** — `concat_shorts`/`extract_frame`/`_write_ass`/`_burn` 변경은 업로드+창작 동시 영향. `create_pipeline.py`가 `caption_maker`의 비공개 함수를 직접 import.
5. **테스트 전무 + 인메모리 상태 휘발** — 회귀 안전망 없음(변경 시 `safe-modify`/`test-generator` 권고), jobs/create_jobs dict는 재시작 시 소실.

---

## 7. 하네스 갱신

코드를 크게 바꾼 뒤에는 **"하네스 업데이트"**(또는 `harness-init` 재실행)로 인덱스(`_workspace/index/*.json`)와 패턴 본문을 다시 추출한다. 패턴만 갱신하려면 **"패턴 추출해줘"**(`pattern-extractor`)를 실행한다.
