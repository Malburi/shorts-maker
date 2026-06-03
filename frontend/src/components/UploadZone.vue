<template>
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
      :disabled="!selectedFile || uploading"
      @click="upload"
    >
      <span v-if="uploading" class="inline-flex items-center gap-2">
        <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
        </svg>
        업로드 중...
      </span>
      <span v-else>쇼츠 만들기 ✨</span>
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const emit = defineEmits(['job-created'])

const fileInput = ref(null)
const selectedFile = ref(null)
const isDragging = ref(false)
const uploading = ref(false)
const aiThumbnail = ref(true)

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

async function upload() {
  if (!selectedFile.value) return
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
</script>
