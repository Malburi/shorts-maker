<template>
  <div class="card p-6 space-y-5">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <p class="text-xs text-gray-500 uppercase tracking-widest mb-1">처리 중</p>
        <h2 class="text-lg font-semibold text-gray-100">{{ job.filename }}</h2>
      </div>
      <StatusBadge :status="job.status" />
    </div>

    <!-- Progress bar -->
    <div>
      <div class="flex justify-between text-sm text-gray-400 mb-1.5">
        <span>{{ job.step }}</span>
        <span>{{ job.progress }}%</span>
      </div>
      <div class="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          class="h-full rounded-full transition-all duration-700"
          :class="job.status === 'error' ? 'bg-red-500' : 'bg-gradient-to-r from-purple-600 to-pink-500'"
          :style="{ width: job.progress + '%' }"
        />
      </div>
    </div>

    <!-- Error -->
    <div v-if="job.status === 'error'" class="bg-red-950/40 border border-red-800 rounded-xl p-4 text-sm text-red-300">
      ⚠️ {{ job.error }}
    </div>

    <!-- Transcript preview -->
    <div v-if="job.transcript_preview" class="bg-gray-800/50 rounded-xl p-4">
      <p class="text-xs text-gray-500 mb-2 uppercase tracking-wide">전사 미리보기</p>
      <p class="text-sm text-gray-300 leading-relaxed">{{ job.transcript_preview }}</p>
    </div>

    <!-- Key moments -->
    <div v-if="job.key_moments?.length">
      <p class="text-xs text-gray-500 mb-3 uppercase tracking-wide">선정된 핵심 장면</p>
      <div class="space-y-2">
        <div
          v-for="m in job.key_moments"
          :key="m.index"
          class="flex items-start gap-3 bg-gray-800/40 rounded-lg p-3"
        >
          <span class="shrink-0 bg-brand-600/30 text-brand-300 text-xs font-bold px-2 py-1 rounded-md">
            #{{ m.index + 1 }}
          </span>
          <div class="min-w-0">
            <p class="font-medium text-gray-200 text-sm truncate">{{ m.title }}</p>
            <p class="text-xs text-gray-500 mt-0.5">
              {{ formatTime(m.start) }} → {{ formatTime(m.end) }}
              ({{ Math.round(m.end - m.start) }}초)
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import StatusBadge from './StatusBadge.vue'

defineProps({ job: Object })

function formatTime(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>
