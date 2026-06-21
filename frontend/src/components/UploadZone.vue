<template>
  <div>
    <!-- Mode toggle -->
    <div class="flex gap-1 mb-4 bg-gray-900 p-1 rounded-xl w-fit">
      <button
        v-for="m in modes"
        :key="m.id"
        class="px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-150"
        :class="mode === m.id
          ? 'bg-brand-600/20 text-brand-300 border border-brand-700/50'
          : 'text-gray-500 hover:text-gray-300'"
        @click="mode = m.id; selectedFile = null; youtubeUrl = ''"
      >
        {{ m.label }}
      </button>
    </div>

    <!-- ── File upload mode ── -->
    <template v-if="mode === 'file'">
      <div
        class="card p-8 text-center cursor-pointer transition-all duration-200"
        :class="[
          isDragging
            ? 'border-brand-500 bg-brand-50/5 scale-[1.01]'
            : 'border-gray-700 hover:border-brand-500/50',
        ]"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="onDrop"
        @click="fileInput?.click()"
      >
        <input
          ref="fileInput"
          type="file"
          accept="video/*"
          class="hidden"
          @change="onFileChange"
        />

        <div v-if="!selectedFile" class="space-y-4">
          <div class="text-6xl">🎬</div>
          <div>
            <p class="text-xl font-semibold text-gray-200">영상을 드래그하거나 클릭해서 업로드</p>
            <p class="text-sm text-gray-500 mt-1">MP4, MOV, AVI, MKV · 최대 500MB</p>
          </div>
        </div>

        <div v-else class="space-y-3">
          <div class="text-5xl">🎥</div>
          <p class="text-lg font-medium text-gray-200">{{ selectedFile.name }}</p>
          <p class="text-sm text-gray-500">{{ formatSize(selectedFile.size) }}</p>
          <button
            class="text-xs text-gray-500 hover:text-red-400 underline"
            @click.stop="selectedFile = null"
          >
            다른 파일 선택
          </button>
        </div>
      </div>
    </template>

    <!-- ── YouTube URL mode ── -->
    <template v-else>
      <div class="card p-8 space-y-4 border-gray-700">
        <div class="flex items-center gap-3">
          <div class="text-5xl">▶️</div>
          <div>
            <p class="text-xl font-semibold text-gray-200">YouTube URL 입력</p>
            <p class="text-sm text-gray-500 mt-0.5">youtube.com 또는 youtu.be 링크</p>
          </div>
        </div>
        <input
          v-model="youtubeUrl"
          type="url"
          placeholder="https://www.youtube.com/watch?v=..."
          class="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-gray-200
                 placeholder-gray-600 focus:outline-none focus:border-brand-500 text-sm"
          @keydown.enter="submit"
        />
        <p v-if="urlError" class="text-xs text-red-400">{{ urlError }}</p>
      </div>
    </template>

    <!-- Bottom bar (shared) -->
    <div class="mt-4 flex items-center gap-4">
      <label class="flex items-center gap-2 cursor-pointer select-none text-sm text-gray-400">
        <input
          v-model="aiThumbnail"
          type="checkbox"
          class="w-4 h-4 accent-purple-500"
        />
        AI 썸네일 생성 (GPT-image-1, 비용 발생)
      </label>
      <div class="flex-1" />
      <button
        class="btn-primary"
        :disabled="!canSubmit || uploading"
        @click="submit"
      >
        <span v-if="uploading" class="inline-flex items-center gap-2">
          <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
          </svg>
          {{ mode === 'youtube' ? '처리 중...' : '업로드 중...' }}
        </span>
        <span v-else>쇼츠 만들기 ✨</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import axios from 'axios'

const emit = defineEmits(['job-created'])

const modes = [
  { id: 'file',    label: '📁 파일 업로드' },
  { id: 'youtube', label: '▶ YouTube URL' },
]
const mode = ref('file')

// file mode
const fileInput = ref(null)
const selectedFile = ref(null)
const isDragging = ref(false)

// youtube mode
const youtubeUrl = ref('')
const urlError = ref('')

// shared
const aiThumbnail = ref(true)
const uploading = ref(false)

const YT_RE = /youtube\.com\/(watch\?.*v=|shorts\/)|youtu\.be\//

const canSubmit = computed(() => {
  if (mode.value === 'file') return !!selectedFile.value
  return youtubeUrl.value.trim().length > 0
})

function onDrop(e) {
  isDragging.value = false
  const file = e.dataTransfer.files[0]
  if (file && file.type.startsWith('video/')) selectedFile.value = file
}

function onFileChange(e) {
  selectedFile.value = e.target.files[0] || null
}

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function submit() {
  if (!canSubmit.value || uploading.value) return
  urlError.value = ''

  if (mode.value === 'youtube') {
    if (!YT_RE.test(youtubeUrl.value)) {
      urlError.value = 'YouTube URL이 아닙니다. youtube.com 또는 youtu.be 링크를 입력하세요.'
      return
    }
    await submitYoutube()
  } else {
    await submitFile()
  }
}

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
    selectedFile.value = null
  } catch (err) {
    alert(err.response?.data?.detail || '업로드 실패: ' + err.message)
  } finally {
    uploading.value = false
  }
}

async function submitYoutube() {
  uploading.value = true
  try {
    const { data } = await axios.post('/api/youtube', {
      url: youtubeUrl.value.trim(),
      ai_thumbnail: aiThumbnail.value,
    })
    emit('job-created', data.job_id)
    youtubeUrl.value = ''
  } catch (err) {
    urlError.value = err.response?.data?.detail || 'YouTube 처리 실패: ' + err.message
  } finally {
    uploading.value = false
  }
}
</script>
