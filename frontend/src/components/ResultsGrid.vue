<template>
  <div>
    <h2 class="text-xl font-bold text-gray-100 mb-5">
      생성된 쇼츠 {{ shorts.length }}개 🎉
    </h2>

    <!-- Highlight reel banner -->
    <div v-if="highlightReelUrl" class="mb-6 card p-5 flex items-center justify-between gap-4 bg-gradient-to-r from-purple-950/60 to-pink-950/50 border border-purple-700/40">
      <div>
        <p class="text-sm font-semibold text-purple-200">하이라이트 릴</p>
        <p class="text-xs text-gray-400 mt-0.5">핵심 장면 {{ shorts.length }}개를 이어붙인 합본</p>
      </div>
      <div class="flex gap-2 shrink-0">
        <button
          class="text-xs bg-gray-800 hover:bg-gray-700 text-gray-200 px-3 py-2 rounded-lg transition-colors font-medium"
          @click="highlightOpen = true"
        >
          ▶ 미리보기
        </button>
        <a
          :href="highlightReelUrl"
          download="highlight_reel.mp4"
          class="text-xs bg-brand-600 hover:bg-brand-700 text-white px-3 py-2 rounded-lg transition-colors font-medium"
        >
          ⬇ 다운로드
        </a>
      </div>
    </div>

    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="s in shorts"
        :key="s.index"
        class="card group flex flex-col"
      >
        <!-- Thumbnail -->
        <div
          class="relative overflow-hidden bg-gray-800 cursor-pointer"
          style="aspect-ratio: 9/16; max-height: 340px;"
          @click="openPlayer(s)"
        >
          <img
            :src="s.thumbnail_url"
            :alt="s.title"
            class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            @error="onImgError($event, s)"
          />
          <!-- Play overlay -->
          <div class="absolute inset-0 flex items-center justify-center
                      bg-black/0 group-hover:bg-black/50 transition-all duration-200">
            <div class="opacity-0 group-hover:opacity-100 transition-opacity duration-200
                        bg-white/20 backdrop-blur-sm rounded-full p-4">
              <svg class="w-10 h-10 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>
          </div>
          <!-- Duration badge -->
          <span class="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-2 py-0.5 rounded font-mono">
            {{ fmtDuration(s.duration) }}
          </span>
          <!-- Index badge -->
          <span class="absolute top-2 left-2 bg-brand-600/90 text-white text-xs font-bold px-2 py-1 rounded-lg">
            #{{ s.index + 1 }}
          </span>
        </div>

        <!-- Info -->
        <div class="p-4 flex flex-col gap-3 flex-1">
          <h3 class="font-bold text-gray-100 text-base leading-snug">{{ s.title }}</h3>

          <!-- Timeline visualization -->
          <div v-if="videoDuration > 0">
            <div class="flex justify-between text-xs text-gray-500 mb-1">
              <span>영상 내 위치</span>
              <span>{{ fmtTime(s.clip_start) }} → {{ fmtTime(s.clip_end) }}</span>
            </div>
            <div class="h-2 bg-gray-700 rounded-full overflow-hidden relative">
              <div
                class="absolute h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full"
                :style="{
                  left: (s.clip_start / videoDuration * 100) + '%',
                  width: ((s.clip_end - s.clip_start) / videoDuration * 100) + '%',
                }"
              />
            </div>
            <div class="flex justify-between text-xs text-gray-600 mt-0.5">
              <span>0:00</span>
              <span>{{ fmtTime(videoDuration) }}</span>
            </div>
          </div>

          <!-- Selection reason -->
          <div class="bg-purple-950/40 border border-purple-800/40 rounded-xl p-3">
            <div class="flex items-center gap-1.5 mb-1.5">
              <span class="text-purple-400 text-sm">💡</span>
              <span class="text-xs font-semibold text-purple-300 uppercase tracking-wide">선정 이유</span>
            </div>
            <p class="text-sm text-gray-300 leading-relaxed">{{ s.reason }}</p>
          </div>

          <!-- Download buttons -->
          <div class="flex gap-2 mt-auto pt-1">
            <a
              :href="s.video_url"
              download
              class="flex-1 text-center text-xs bg-brand-600 hover:bg-brand-700
                     text-white py-2 rounded-lg transition-colors font-medium"
              @click.stop
            >
              ⬇ 쇼츠 다운로드
            </a>
            <a
              :href="s.thumbnail_url"
              download
              class="flex-1 text-center text-xs bg-gray-700 hover:bg-gray-600
                     text-white py-2 rounded-lg transition-colors font-medium"
              @click.stop
            >
              🖼 썸네일
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- Highlight reel modal -->
    <Teleport to="body">
      <div
        v-if="highlightOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
        @click.self="highlightOpen = false"
      >
        <div class="relative">
          <button
            class="absolute -top-9 right-0 text-gray-300 hover:text-white text-sm px-3 py-1 rounded-lg bg-gray-800"
            @click="highlightOpen = false"
          >
            닫기 ✕
          </button>
          <video
            :src="highlightReelUrl"
            controls
            autoplay
            class="rounded-xl shadow-2xl"
            style="max-height: 85vh; max-width: min(480px, 90vw);"
          />
        </div>
      </div>
    </Teleport>

    <!-- Video modal -->
    <Teleport to="body">
      <div
        v-if="activeShort"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
        @click.self="activeShort = null"
      >
        <div class="relative flex gap-6 items-start max-h-[90vh]">
          <!-- Close -->
          <button
            class="absolute -top-9 right-0 text-gray-300 hover:text-white text-sm px-3 py-1 rounded-lg bg-gray-800"
            @click="activeShort = null"
          >
            닫기 ✕
          </button>

          <!-- Video -->
          <video
            :src="activeShort.video_url"
            controls
            autoplay
            class="rounded-xl shadow-2xl"
            style="max-height: 85vh; max-width: min(380px, 45vw);"
          />

          <!-- Info panel -->
          <div class="hidden md:flex flex-col gap-4 max-w-xs text-sm">
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-widest mb-1">제목</p>
              <p class="text-gray-100 font-semibold text-base">{{ activeShort.title }}</p>
            </div>

            <div v-if="videoDuration > 0">
              <p class="text-xs text-gray-500 uppercase tracking-widest mb-2">영상 내 위치</p>
              <div class="h-2.5 bg-gray-700 rounded-full overflow-hidden relative">
                <div
                  class="absolute h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full"
                  :style="{
                    left: (activeShort.clip_start / videoDuration * 100) + '%',
                    width: ((activeShort.clip_end - activeShort.clip_start) / videoDuration * 100) + '%',
                  }"
                />
              </div>
              <div class="flex justify-between text-xs text-gray-500 mt-1">
                <span>{{ fmtTime(activeShort.clip_start) }}</span>
                <span>{{ fmtDuration(activeShort.duration) }}</span>
                <span>{{ fmtTime(activeShort.clip_end) }}</span>
              </div>
            </div>

            <div class="bg-purple-950/50 border border-purple-800/40 rounded-xl p-4">
              <div class="flex items-center gap-1.5 mb-2">
                <span class="text-purple-400">💡</span>
                <span class="text-xs font-semibold text-purple-300 uppercase tracking-wide">선정 이유</span>
              </div>
              <p class="text-gray-300 leading-relaxed">{{ activeShort.reason }}</p>
            </div>

            <div class="flex flex-col gap-2">
              <a :href="activeShort.video_url" download
                 class="text-center text-sm bg-brand-600 hover:bg-brand-700 text-white py-2.5 rounded-xl transition-colors font-medium">
                ⬇ 쇼츠 다운로드
              </a>
              <a :href="activeShort.thumbnail_url" download
                 class="text-center text-sm bg-gray-700 hover:bg-gray-600 text-white py-2.5 rounded-xl transition-colors font-medium">
                🖼 썸네일 다운로드
              </a>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  shorts: Array,
  videoDuration: { type: Number, default: 0 },
  highlightReelUrl: { type: String, default: null },
})

const activeShort = ref(null)
const highlightOpen = ref(false)

function openPlayer(s) { activeShort.value = s }

function fmtTime(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}

function fmtDuration(s) {
  if (s >= 60) return `${Math.floor(s / 60)}분 ${Math.floor(s % 60)}초`
  return `${Math.floor(s)}초`
}

function onImgError(e) {
  e.target.src = `data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='108' height='192'><rect fill='%23374151'/><text x='50%25' y='50%25' fill='%239ca3af' text-anchor='middle' font-size='24'>🎬</text></svg>`
}
</script>
