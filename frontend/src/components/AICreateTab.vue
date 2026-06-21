<template>
  <div class="space-y-8">

    <!-- ── PHASE: INPUT (단일 프롬프트) ──────────────────────────────── -->
    <template v-if="phase === 'input'">
      <!-- Hero -->
      <div class="text-center space-y-3 mb-8">
        <h1 class="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-violet-400 to-fuchsia-400">
          프롬프트 하나로 일관성 있는 숏폼
        </h1>
        <p class="text-gray-500 max-w-md mx-auto">
          원하는 내용·분위기·길이를 한 번에 적어주세요<br>
          → 통일된 화풍의 대본 작성 → 기준 이미지 + Veo 영상 자동 생성
        </p>
      </div>

      <!-- Prompt input -->
      <div class="card p-6 space-y-4">
        <label class="text-sm font-medium text-gray-300">어떤 숏폼을 만들까요?</label>
        <textarea
          v-model="promptInput"
          rows="5"
          class="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-gray-100
                 placeholder-gray-600 focus:outline-none focus:border-violet-500 transition-colors resize-none"
          placeholder="예: 네덜란드 역사를 60초로 요약. 따뜻한 수채화풍 일러스트, 잔잔하고 감성적인 톤. 한 명의 내레이터 시점으로 차분하게."
          @keydown.ctrl.enter="generateScript"
          @keydown.meta.enter="generateScript"
        />
        <div class="flex items-center justify-between">
          <p class="text-xs text-gray-600">주제 · 화풍/분위기 · 길이(30/60/90초)를 자유롭게 적으면 됩니다 · Ctrl+Enter</p>
          <button
            class="px-6 py-3 bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500
                   hover:to-fuchsia-500 text-white font-semibold rounded-xl transition-all duration-150
                   disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            :disabled="!promptInput.trim() || loading"
            @click="generateScript"
          >
            <div v-if="loading" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            <span v-if="loading">검색 + 대본 작성 중...</span>
            <span v-else>대본 만들기 →</span>
          </button>
        </div>
        <p v-if="loading" class="text-xs text-gray-600">실시간 데이터를 수집해 일관성 있는 대본을 작성하고 있어요</p>
      </div>

      <!-- Error -->
      <div v-if="inputError" class="bg-red-950/40 border border-red-800 rounded-xl p-4 text-sm text-red-300">
        {{ inputError }}
        <button class="ml-3 underline text-red-400 hover:text-red-300" @click="generateScript">재시도</button>
      </div>
    </template>

    <!-- ── PHASE: PREVIEW ────────────────────────────────────────────── -->
    <template v-if="phase === 'preview'">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xl font-bold text-gray-100">대본 미리보기</h2>
          <p class="text-sm text-gray-500 mt-1">통일 스타일과 장면을 수정한 뒤 생성을 시작하세요</p>
        </div>
        <button class="text-xs text-gray-500 hover:text-gray-300 underline" @click="resetAll">
          처음부터
        </button>
      </div>

      <!-- 웹 검색 기반 배지 -->
      <div v-if="searchCount > 0" class="bg-emerald-950/40 border border-emerald-800/50 rounded-xl p-3 flex flex-col gap-2">
        <div class="flex items-center gap-2">
          <span class="text-emerald-400 text-sm font-semibold">실시간 웹 검색 {{ searchCount }}건 기반 대본</span>
        </div>
        <div v-if="searchSnippets.length" class="flex flex-wrap gap-1.5">
          <span
            v-for="(s, i) in searchSnippets"
            :key="i"
            class="text-xs bg-emerald-900/40 text-emerald-400 px-2 py-0.5 rounded-full border border-emerald-800/40 truncate max-w-xs"
            :title="s"
          >
            {{ s }}
          </span>
        </div>
      </div>

      <!-- Script title -->
      <div class="card p-4 flex items-center gap-3">
        <span class="text-violet-400 font-bold">제목</span>
        <input
          v-model="script.title"
          class="flex-1 bg-transparent text-gray-100 font-semibold focus:outline-none
                 border-b border-gray-700 focus:border-violet-500 pb-0.5"
        />
        <span class="text-xs text-gray-600">목표 {{ script.target_duration }}초 · {{ script.scenes.length }}개 장면</span>
      </div>

      <!-- 통일 비주얼 스타일 (기준 이미지) -->
      <div class="card p-4 space-y-2 border-violet-800/40">
        <div class="flex items-center gap-2">
          <span class="bg-fuchsia-600/30 text-fuchsia-300 text-xs font-bold px-2 py-0.5 rounded">통일 스타일 · 기준 이미지</span>
          <span class="text-xs text-gray-600">모든 장면이 이 화풍·인물·배경을 따릅니다</span>
        </div>
        <textarea
          v-model="script.visual_style"
          rows="3"
          class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-300
                 focus:outline-none focus:border-violet-500 resize-none transition-colors font-mono"
          placeholder="전체 영상의 통일된 화풍·색감·조명·등장 인물/피사체·배경 (영어)"
        />
      </div>

      <!-- Scene cards -->
      <div class="space-y-3">
        <div
          v-for="(scene, i) in script.scenes"
          :key="i"
          class="card p-4 space-y-3"
        >
          <div class="flex items-center gap-2 mb-1">
            <span class="bg-violet-600/30 text-violet-300 text-xs font-bold px-2 py-0.5 rounded">
              장면 {{ scene.order }}
            </span>
          </div>

          <div>
            <label class="text-xs text-gray-500 uppercase tracking-wide block mb-1">나레이션 (TTS)</label>
            <textarea
              v-model="script.scenes[i].narration"
              rows="2"
              class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200
                     focus:outline-none focus:border-violet-500 resize-none transition-colors"
            />
          </div>

          <div>
            <label class="text-xs text-gray-500 uppercase tracking-wide block mb-1">장면 묘사 (이 장면 고유)</label>
            <textarea
              v-model="script.scenes[i].image_prompt"
              rows="2"
              class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-400
                     focus:outline-none focus:border-violet-500 resize-none transition-colors font-mono"
            />
          </div>
        </div>
      </div>

      <div class="flex gap-3">
        <button
          class="flex-1 py-3 bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500
                 hover:to-fuchsia-500 text-white font-bold rounded-xl transition-all duration-150 text-sm"
          @click="generateVideo"
        >
          영상 생성 시작
        </button>
      </div>
    </template>

    <!-- ── PHASE: GENERATING ─────────────────────────────────────────── -->
    <template v-if="phase === 'generating'">
      <div class="card p-6 space-y-5">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-xs text-gray-500 uppercase tracking-widest mb-1">AI 창작 중</p>
            <h2 class="text-lg font-semibold text-gray-100">{{ script?.title }}</h2>
          </div>
          <span
            class="text-xs px-3 py-1 rounded-full font-medium"
            :class="job?.status === 'error' ? 'bg-red-900/50 text-red-300' : 'bg-violet-900/50 text-violet-300'"
          >
            {{ job?.status === 'error' ? '오류' : '처리 중' }}
          </span>
        </div>

        <!-- Progress bar -->
        <div>
          <div class="flex justify-between text-sm text-gray-400 mb-1.5">
            <span>{{ job?.step ?? '준비 중...' }}</span>
            <span>{{ job?.progress ?? 0 }}%</span>
          </div>
          <div class="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-700"
              :class="job?.status === 'error' ? 'bg-red-500' : 'bg-gradient-to-r from-violet-600 to-fuchsia-500'"
              :style="{ width: (job?.progress ?? 0) + '%' }"
            />
          </div>
        </div>

        <!-- Error -->
        <div v-if="job?.status === 'error'" class="bg-red-950/40 border border-red-800 rounded-xl p-4 text-sm text-red-300 space-y-2">
          <p>{{ job.error }}</p>
          <button class="underline text-red-400 hover:text-red-300 text-xs" @click="resetAll">처음부터 다시</button>
        </div>

        <!-- Scenes hint -->
        <div v-if="script?.scenes?.length" class="bg-gray-800/40 rounded-xl p-4">
          <p class="text-xs text-gray-500 mb-2 uppercase tracking-wide">생성 중인 장면</p>
          <div class="space-y-1">
            <div
              v-for="(scene, i) in script.scenes"
              :key="i"
              class="flex items-center gap-2 text-sm text-gray-400"
            >
              <span class="text-xs text-violet-500 shrink-0">{{ scene.order }}</span>
              <span class="truncate">{{ scene.narration.substring(0, 40) }}...</span>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ── PHASE: DONE ───────────────────────────────────────────────── -->
    <template v-if="phase === 'done'">
      <div class="flex items-center justify-between">
        <h2 class="text-xl font-bold text-gray-100">생성 완료</h2>
        <button
          class="text-xs text-gray-500 hover:text-gray-300 underline"
          @click="resetAll"
        >
          새 영상 만들기
        </button>
      </div>

      <div class="flex flex-col md:flex-row gap-6 items-start">
        <!-- Video preview -->
        <div
          class="relative overflow-hidden bg-gray-800 rounded-2xl cursor-pointer group shrink-0"
          style="width: min(280px, 100%); aspect-ratio: 9/16;"
          @click="playerOpen = true"
        >
          <img
            v-if="job?.thumbnail_url"
            :src="job.thumbnail_url"
            class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
          />
          <div class="absolute inset-0 flex items-center justify-center
                      bg-black/0 group-hover:bg-black/50 transition-all duration-200">
            <div class="opacity-0 group-hover:opacity-100 transition-opacity duration-200
                        bg-white/20 backdrop-blur-sm rounded-full p-4">
              <svg class="w-10 h-10 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>
          </div>
        </div>

        <!-- Info + download -->
        <div class="flex-1 space-y-4">
          <div>
            <p class="text-xs text-gray-500 uppercase tracking-wide mb-1">제목</p>
            <p class="text-lg font-bold text-gray-100">{{ script?.title }}</p>
          </div>

          <div>
            <p class="text-xs text-gray-500 uppercase tracking-wide mb-2">장면 구성</p>
            <div class="space-y-1.5">
              <div
                v-for="(scene, i) in script?.scenes"
                :key="i"
                class="flex items-start gap-2 bg-gray-800/40 rounded-lg px-3 py-2"
              >
                <span class="text-xs text-violet-400 font-bold shrink-0 mt-0.5">{{ scene.order }}</span>
                <p class="text-xs text-gray-400 leading-relaxed">{{ scene.narration }}</p>
              </div>
            </div>
          </div>

          <div class="flex flex-col gap-2 pt-2">
            <a
              :href="job?.video_url"
              download="shortform.mp4"
              class="text-center text-sm bg-gradient-to-r from-violet-600 to-fuchsia-600
                     hover:from-violet-500 hover:to-fuchsia-500 text-white py-3 rounded-xl
                     transition-all font-bold"
            >
              완성 영상 다운로드
            </a>
            <a
              :href="job?.thumbnail_url"
              download="thumbnail.jpg"
              class="text-center text-sm bg-gray-700 hover:bg-gray-600 text-white py-2.5 rounded-xl
                     transition-colors font-medium"
            >
              썸네일 다운로드
            </a>
          </div>
        </div>
      </div>

      <!-- Video modal -->
      <Teleport to="body">
        <div
          v-if="playerOpen"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
          @click.self="playerOpen = false"
        >
          <div class="relative">
            <button
              class="absolute -top-9 right-0 text-gray-300 hover:text-white text-sm px-3 py-1 rounded-lg bg-gray-800"
              @click="playerOpen = false"
            >
              닫기 ✕
            </button>
            <video
              :src="job?.video_url"
              controls
              autoplay
              class="rounded-xl shadow-2xl"
              style="max-height: 85vh; max-width: min(400px, 90vw);"
            />
          </div>
        </div>
      </Teleport>
    </template>

  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const phase = ref('input')       // 'input' | 'preview' | 'generating' | 'done'
const promptInput = ref('')
const loading = ref(false)
const inputError = ref('')
const searchCount = ref(0)
const searchSnippets = ref([])
const script = ref(null)         // ScriptData (visual_style 포함)
const jobId = ref(null)
const job = ref(null)
const playerOpen = ref(false)

let eventSource = null

async function generateScript() {
  if (!promptInput.value.trim() || loading.value) return
  loading.value = true
  inputError.value = ''
  try {
    const { data } = await axios.post('/api/create/script', {
      prompt: promptInput.value.trim(),
    })
    script.value = data.script
    searchCount.value = data.search_count ?? 0
    searchSnippets.value = data.search_snippets ?? []
    phase.value = 'preview'
  } catch (e) {
    inputError.value = e.response?.data?.detail ?? e.message ?? '대본 생성 중 오류가 발생했습니다.'
  } finally {
    loading.value = false
  }
}

async function generateVideo() {
  phase.value = 'generating'
  try {
    const { data } = await axios.post('/api/create/generate', { script: script.value })
    jobId.value = data.job_id
    startSSE(data.job_id)
  } catch (e) {
    phase.value = 'preview'
    alert('생성 시작 실패: ' + (e.response?.data?.detail ?? e.message))
  }
}

function startSSE(id) {
  eventSource?.close()
  eventSource = new EventSource(`/api/create/jobs/${id}/events`)
  eventSource.onmessage = (e) => {
    job.value = JSON.parse(e.data)
    if (job.value.status === 'done') {
      phase.value = 'done'
      eventSource.close()
    } else if (job.value.status === 'error') {
      eventSource.close()
    }
  }
  eventSource.onerror = () => eventSource.close()
}

function resetAll() {
  eventSource?.close()
  phase.value = 'input'
  promptInput.value = ''
  loading.value = false
  inputError.value = ''
  searchCount.value = 0
  searchSnippets.value = []
  script.value = null
  jobId.value = null
  job.value = null
  playerOpen.value = false
}
</script>
