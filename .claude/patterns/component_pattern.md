# Frontend Component Pattern — Shorts Maker (Modern SPA)

추출 시각: 2026-06-17
샘플 파일 수: 5 (App.vue, UploadZone.vue, ResultsGrid.vue, ChatPanel.vue 통독 + AICreateTab.vue 참조)
신뢰도: HIGH (전 컴포넌트 구조 확인, Vue 3 SFC 패턴 일관)

---

## 권장 패턴

### Vue 3 SFC 구조 — script setup 전면 사용
빈도: 100% (확인한 5개 컴포넌트 모두)

```vue
<template>
  <!-- Tailwind CSS 클래스로 스타일링 -->
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'
import SomeComponent from './SomeComponent.vue'
// ...

// props 선언
const props = defineProps({
  shorts: Array,
  videoDuration: { type: Number, default: 0 },
  jobId: { type: String, default: null },
})

// emits 선언
const emit = defineEmits(['job-created'])

// 반응형 상태
const activeTab = ref('create')
const uploading = ref(false)

// computed
const canSubmit = computed(() => !!selectedFile.value)

// 생명주기
onUnmounted(() => eventSource?.close())
</script>
```

Options API 사용 없음. `<style scoped>` 없음 — 전부 Tailwind 인라인.

---

### Tailwind CSS 클래스 사용 관례

```vue
<!-- 다크 테마: gray-950(배경), gray-800(카드), gray-100/200(텍스트) -->
<div class="min-h-screen bg-gray-950">

<!-- 커스텀 컴포넌트 클래스 (tailwind.config 정의 추정) -->
<div class="card">           <!-- 카드 컨테이너 -->
<button class="btn-primary"> <!-- 주요 액션 버튼 -->

<!-- 브랜드 컬러 (brand-*) -->
<div class="bg-brand-600/20 text-brand-300 border border-brand-700/50">

<!-- 반응형 그리드 -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">

<!-- 상태 기반 조건부 클래스 -->
:class="activeTab === tab.id
  ? 'bg-brand-600/20 text-brand-300 border border-brand-700/50'
  : 'text-gray-500 hover:text-gray-300'"

<!-- 호버 + 트랜지션 패턴 -->
class="group-hover:scale-105 transition-transform duration-300"
class="opacity-0 group-hover:opacity-100 transition-opacity duration-200"
```

---

### API 호출 패턴 — axios (대부분) + fetch (ChatPanel)

```javascript
// axios — 대부분의 API 호출 (UploadZone.vue 예시)
import axios from 'axios'

async function submitFile() {
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', selectedFile.value)
    const { data } = await axios.post(
      `/api/upload?ai_thumbnail=${aiThumbnail.value}`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    emit('job-created', data.job_id)
  } catch (err) {
    alert(err.response?.data?.detail || '업로드 실패: ' + err.message)
  } finally {
    uploading.value = false
  }
}

// 에러 메시지: err.response?.data?.detail (FastAPI HTTPException.detail 필드)
// fallback: err.message
```

Vite proxy (`vite.config.js`): `/api`, `/outputs`, `/create_outputs` → `http://localhost:8000`

---

### 컴포넌트 통신 패턴

```javascript
// 부모 → 자식: props
const props = defineProps({
  shorts: Array,
  videoDuration: { type: Number, default: 0 },
  highlightReelUrl: { type: String, default: null },
  jobId: { type: String, default: null },
  hasKnowledge: { type: Boolean, default: false },
})

// 자식 → 부모: emit
const emit = defineEmits(['job-created'])
emit('job-created', data.job_id)

// 부모 처리
<UploadZone @job-created="onJobCreated" />
function onJobCreated(id) {
  jobId.value = id
  startSSE(id)
}
```

---

### 탭 셸 패턴 (App.vue)

```javascript
const tabs = [
  { id: 'create',    label: '🎬 새 쇼츠 만들기' },
  { id: 'ai-create', label: '✨ AI 창작' },
  { id: 'history',   label: '📂 히스토리' },
]
const activeTab = ref('create')

function switchTab(id) {
  activeTab.value = id
}
```

```vue
<!-- 탭 렌더링: v-if로 조건부 마운트 (v-show 아님 — 언마운트 방식) -->
<template v-if="activeTab === 'create'">...</template>
<template v-if="activeTab === 'ai-create'">...</template>
<template v-if="activeTab === 'history'">...</template>
```

---

### SSE EventSource 연결 생명주기

```javascript
// App.vue — 업로드 파이프라인 SSE
let eventSource = null   // 모듈 스코프 변수 (ref 아님 — 반응성 불필요)

function startSSE(id) {
  eventSource?.close()
  eventSource = new EventSource(`/api/jobs/${id}/events`)

  eventSource.onmessage = (e) => {
    job.value = JSON.parse(e.data)
    if (job.value.status === 'done' || job.value.status === 'error') {
      eventSource.close()
      historyKey.value++             // 완료 시 히스토리 자동 새로고침
    }
  }

  eventSource.onerror = () => eventSource.close()
}

onUnmounted(() => eventSource?.close())   // 메모리 누수 방지
```

---

### 썸네일 토글 패턴 (ResultsGrid.vue)

```javascript
// Set 기반 토글 (Vue 반응성 트리거를 위해 새 Set 생성)
const previewSet = ref(new Set())

function togglePreview(index) {
  const s = new Set(previewSet.value)
  s.has(index) ? s.delete(index) : s.add(index)
  previewSet.value = s   // 새 Set 할당으로 반응성 트리거
}
```

```vue
<!-- AI 썸네일 vs 원본 프레임 조건부 표시 -->
:src="previewSet.has(s.index) && s.preview_frame_url
      ? s.preview_frame_url
      : s.thumbnail_url"
```

---

### 모달 패턴 — Teleport to body

```vue
<Teleport to="body">
  <div
    v-if="activeShort"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
    @click.self="activeShort = null"    <!-- 배경 클릭으로 닫기 -->
  >
    <div class="relative">
      <button
        class="absolute -top-9 right-0 ..."
        @click="activeShort = null"
      >닫기 ✕</button>
      <video :src="activeShort.video_url" controls autoplay .../>
    </div>
  </div>
</Teleport>
```

`Teleport to="body"` 패턴 — z-index 중첩 문제 방지. 배경 클릭 닫기는 `@click.self`.

---

### 이미지 에러 폴백

```javascript
// ResultsGrid.vue
function onImgError(e) {
  e.target.src = `data:image/svg+xml,<svg ...><rect fill='%23374151'/><text ...>🎬</text></svg>`
}
```

인라인 SVG data URI로 플레이스홀더 대체. `@error="onImgError($event, s)"` 이벤트 핸들러.

---

### 다운로드 링크 패턴

```vue
<!-- 직접 다운로드 — <a> 태그 + download 속성 -->
<a
  :href="s.video_url"
  download
  class="flex-1 text-center text-xs bg-brand-600 hover:bg-brand-700 text-white py-2 rounded-lg"
  @click.stop
>
  ⬇ 쇼츠 다운로드
</a>
```

`@click.stop` — 부모 클릭 이벤트 전파 방지 (카드 클릭 → 플레이어 오픈 이벤트 차단).

---

## 안티패턴 (피해야 할 패턴)

### EventSource onerror — 재연결 없음
- 위치: `App.vue:130`
- 현황: `eventSource.onerror = () => eventSource.close()` — 에러 시 닫기만 함
- 권고: 지수 백오프 재연결 로직 추가 (sse_pattern.md 참조)

### axios와 fetch 혼용
- 위치: 대부분 axios, ChatPanel은 fetch 사용
- 권고: 신규 컴포넌트는 axios 통일 (에러 처리 일관성)

### alert() 사용
- 위치: `UploadZone.vue:187` `alert(err.response?.data?.detail || ...)`
- 권고: 인라인 에러 메시지 표시 (`ref('')` + `v-if="error"`)

---

## 신규 컴포넌트 작성 가이드

1. `<script setup>` 필수 사용
2. 스타일: Tailwind 인라인 클래스 (별도 CSS 파일 금지)
3. API 호출: axios 사용, `try/catch/finally` + `err.response?.data?.detail` 에러 추출
4. 로딩 상태: `const uploading = ref(false)` + `finally { uploading.value = false }`
5. 부모 통신: props + emit 패턴 (Vuex/Pinia 미사용)
6. 모달: `<Teleport to="body">` + `v-if` + `@click.self` 닫기
7. SSE가 필요한 경우 App.vue의 `startSSE` 패턴 참조 (onUnmounted 정리 필수)
8. 이미지 로드 실패: `@error` 핸들러 + data URI 플레이스홀더
