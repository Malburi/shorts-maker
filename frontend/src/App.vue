<template>
  <div class="min-h-screen bg-gray-950">
    <!-- Header -->
    <header class="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-10">
      <div class="max-w-5xl mx-auto px-4 h-14 flex items-center gap-3">
        <span class="text-2xl">⚡</span>
        <span class="font-bold text-gray-100 text-lg">Shorts Maker</span>
        <span class="text-xs text-gray-600 ml-1">by Gemini AI</span>

        <!-- Tabs -->
        <nav class="flex-1 flex justify-center gap-1">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            class="px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-150"
            :class="activeTab === tab.id
              ? 'bg-brand-600/20 text-brand-300 border border-brand-700/50'
              : 'text-gray-500 hover:text-gray-300'"
            @click="switchTab(tab.id)"
          >
            {{ tab.label }}
          </button>
        </nav>

        <button
          v-if="activeTab === 'create' && jobId"
          class="text-xs text-gray-500 hover:text-gray-300 underline"
          @click="reset"
        >
          새 영상 만들기
        </button>
      </div>
    </header>

    <main class="max-w-5xl mx-auto px-4 py-10 space-y-8">

      <!-- ── CREATE TAB ── -->
      <template v-if="activeTab === 'create'">
        <!-- Hero (only before first upload) -->
        <div v-if="!jobId" class="text-center space-y-3 mb-8">
          <h1 class="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-400">
            영상 → 쇼츠 자동 변환
          </h1>
          <p class="text-gray-500 max-w-md mx-auto">
            영상을 업로드하면 AI가 핵심 장면을 자동으로 선정하고<br>쇼츠 클립 + 썸네일을 만들어 드립니다
          </p>
        </div>

        <UploadZone v-if="!jobId" @job-created="onJobCreated" />

        <ProgressPanel v-if="job && job.status !== 'done'" :job="job" />

        <ResultsGrid
          v-if="job?.shorts?.length"
          :shorts="job.shorts"
          :video-duration="job.video_duration ?? 0"
          :highlight-reel-url="job.highlight_reel_url ?? null"
        />
      </template>

      <!-- ── HISTORY TAB ── -->
      <template v-if="activeTab === 'history'">
        <div class="flex items-center justify-between mb-2">
          <h2 class="text-xl font-bold text-gray-100">처리 히스토리</h2>
          <button
            class="text-xs text-gray-500 hover:text-gray-300 underline"
            @click="refreshHistory"
          >
            새로고침
          </button>
        </div>
        <HistoryPanel :key="historyKey" />
      </template>

    </main>
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import UploadZone from './components/UploadZone.vue'
import ProgressPanel from './components/ProgressPanel.vue'
import ResultsGrid from './components/ResultsGrid.vue'
import HistoryPanel from './components/HistoryPanel.vue'

const tabs = [
  { id: 'create',  label: '🎬 새 쇼츠 만들기' },
  { id: 'history', label: '📂 히스토리' },
]

const activeTab = ref('create')
const jobId = ref(null)
const job = ref(null)
const historyKey = ref(0)
let eventSource = null

function switchTab(id) {
  activeTab.value = id
}

function refreshHistory() {
  historyKey.value++
}

function onJobCreated(id) {
  jobId.value = id
  startSSE(id)
}

function startSSE(id) {
  eventSource?.close()
  eventSource = new EventSource(`/api/jobs/${id}/events`)
  eventSource.onmessage = (e) => {
    job.value = JSON.parse(e.data)
    if (job.value.status === 'done' || job.value.status === 'error') {
      eventSource.close()
      // Auto-refresh history when a job completes
      historyKey.value++
    }
  }
  eventSource.onerror = () => eventSource.close()
}

function reset() {
  eventSource?.close()
  jobId.value = null
  job.value = null
}

onUnmounted(() => eventSource?.close())
</script>
