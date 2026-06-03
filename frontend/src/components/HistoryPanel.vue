<template>
  <div class="space-y-6">

    <!-- Loading -->
    <div v-if="loading" class="text-center py-16 text-gray-500">
      <div class="text-4xl mb-3 animate-spin inline-block">⚙️</div>
      <p>히스토리 로딩 중...</p>
    </div>

    <!-- Empty -->
    <div v-else-if="!items.length" class="text-center py-16 text-gray-500">
      <div class="text-5xl mb-4">📭</div>
      <p class="text-lg font-medium text-gray-400">처리된 영상이 없습니다</p>
      <p class="text-sm mt-1">영상을 업로드하면 여기에 기록됩니다</p>
    </div>

    <!-- List -->
    <div v-else class="space-y-3">
      <TransitionGroup name="list">
        <div
          v-for="item in items"
          :key="item.id"
          class="card overflow-visible cursor-pointer hover:border-gray-600 transition-colors"
          :class="expanded === item.id ? 'border-purple-700/60' : ''"
        >
          <!-- Header row -->
          <div class="p-4 flex items-center gap-4" @click="toggle(item.id)">
            <!-- Thumb strip -->
            <div class="flex gap-1 shrink-0">
              <div
                v-for="s in item.shorts.slice(0, 3)"
                :key="s.index"
                class="w-10 rounded overflow-hidden bg-gray-800"
                style="aspect-ratio: 9/16;"
              >
                <img :src="s.thumbnail_url" class="w-full h-full object-cover" @error="e => e.target.src=''"/>
              </div>
              <div
                v-if="item.shorts.length > 3"
                class="w-10 rounded bg-gray-700 flex items-center justify-center text-xs text-gray-400 font-bold"
                style="aspect-ratio: 9/16;"
              >+{{ item.shorts.length - 3 }}</div>
            </div>

            <!-- Meta -->
            <div class="flex-1 min-w-0">
              <p class="font-semibold text-gray-100 truncate">{{ item.filename }}</p>
              <div class="flex items-center gap-3 mt-1 flex-wrap">
                <span class="text-xs text-gray-500">{{ fmtDate(item.completed_at) }}</span>
                <span class="text-xs bg-brand-600/30 text-brand-300 px-2 py-0.5 rounded-full">
                  쇼츠 {{ item.shorts.length }}개
                </span>
                <span v-if="item.video_duration" class="text-xs text-gray-600">
                  {{ fmtTime(item.video_duration) }}
                </span>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex items-center gap-2 shrink-0" @click.stop>
              <button
                class="p-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-red-950/40 transition-colors"
                title="삭제"
                @click="confirmDelete(item)"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                </svg>
              </button>
              <svg
                class="w-5 h-5 text-gray-500 transition-transform duration-200"
                :class="expanded === item.id ? 'rotate-180' : ''"
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
                @click="toggle(item.id)"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
              </svg>
            </div>
          </div>

          <!-- Expanded shorts -->
          <div v-if="expanded === item.id" class="border-t border-gray-800 p-4" @click.stop>

            <!-- Transcript preview -->
            <div v-if="item.transcript_preview" class="bg-gray-800/60 rounded-xl p-3 mb-4">
              <p class="text-xs text-gray-500 mb-1 uppercase tracking-wide">전사 미리보기</p>
              <p class="text-sm text-gray-300 leading-relaxed">{{ item.transcript_preview }}</p>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <div v-for="s in item.shorts" :key="s.index"
                   class="bg-gray-800/50 rounded-xl overflow-hidden">
                <!-- Thumb -->
                <div class="relative cursor-pointer group" style="aspect-ratio:9/16;max-height:220px;"
                     @click="openPlayer(s)">
                  <img :src="s.thumbnail_url"
                       class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                       @error="e => e.target.src=''"/>
                  <div class="absolute inset-0 flex items-center justify-center
                              bg-black/0 group-hover:bg-black/50 transition-all">
                    <svg class="w-8 h-8 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                         fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                  </div>
                  <span class="absolute bottom-1 right-1 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded font-mono">
                    {{ fmtDuration(s.duration) }}
                  </span>
                </div>

                <!-- Card body -->
                <div class="p-3 space-y-2">
                  <p class="font-semibold text-gray-100 text-sm leading-snug">{{ s.title }}</p>

                  <!-- Timeline -->
                  <div v-if="item.video_duration > 0">
                    <div class="h-1.5 bg-gray-700 rounded-full overflow-hidden relative">
                      <div class="absolute h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full"
                           :style="{
                             left: (s.clip_start / item.video_duration * 100) + '%',
                             width: ((s.clip_end - s.clip_start) / item.video_duration * 100) + '%',
                           }"/>
                    </div>
                    <p class="text-xs text-gray-600 mt-0.5">
                      {{ fmtTime(s.clip_start) }} → {{ fmtTime(s.clip_end) }}
                    </p>
                  </div>

                  <!-- Reason -->
                  <div class="bg-purple-950/40 border border-purple-800/30 rounded-lg p-2.5">
                    <p class="text-xs text-purple-300 font-semibold mb-0.5">💡 선정 이유</p>
                    <p class="text-xs text-gray-300 leading-relaxed">{{ s.reason }}</p>
                  </div>

                  <div class="flex gap-1.5">
                    <a :href="s.video_url" download
                       class="flex-1 text-center text-xs bg-brand-600 hover:bg-brand-700 text-white py-1.5 rounded-lg transition-colors">⬇ 쇼츠</a>
                    <a :href="s.thumbnail_url" download
                       class="flex-1 text-center text-xs bg-gray-700 hover:bg-gray-600 text-white py-1.5 rounded-lg transition-colors">🖼 썸네일</a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </TransitionGroup>
    </div>

    <!-- Delete confirm modal -->
    <Teleport to="body">
      <div v-if="deleteTarget"
           class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
           @click.self="deleteTarget = null">
        <div class="card p-6 w-full max-w-sm mx-4 space-y-4">
          <h3 class="font-bold text-gray-100 text-lg">삭제 확인</h3>
          <p class="text-gray-400 text-sm leading-relaxed">
            <span class="text-gray-200 font-medium">{{ deleteTarget.filename }}</span>의
            쇼츠 {{ deleteTarget.shorts.length }}개와 썸네일이 모두 삭제됩니다.
            <br>이 작업은 되돌릴 수 없습니다.
          </p>
          <div class="flex gap-3">
            <button
              class="flex-1 py-2 rounded-xl bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm font-medium transition-colors"
              @click="deleteTarget = null"
            >취소</button>
            <button
              class="flex-1 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-sm font-medium transition-colors"
              :disabled="deleting"
              @click="doDelete"
            >
              <span v-if="deleting">삭제 중...</span>
              <span v-else>삭제</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Video modal -->
    <Teleport to="body">
      <div v-if="activeShort"
           class="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
           @click.self="activeShort = null">
        <div class="relative">
          <button class="absolute -top-9 right-0 text-gray-300 hover:text-white text-sm px-3 py-1 rounded-lg bg-gray-800"
                  @click="activeShort = null">닫기 ✕</button>
          <video :src="activeShort.video_url" controls autoplay class="rounded-xl shadow-2xl"
                 style="max-height:85vh;max-width:min(400px,90vw);"/>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const items = ref([])
const loading = ref(true)
const expanded = ref(null)
const activeShort = ref(null)
const deleteTarget = ref(null)
const deleting = ref(false)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/history')
    items.value = data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function toggle(id) {
  expanded.value = expanded.value === id ? null : id
}

function openPlayer(s) { activeShort.value = s }

function confirmDelete(item) {
  deleteTarget.value = item
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await axios.delete(`/api/history/${deleteTarget.value.id}`)
    items.value = items.value.filter(i => i.id !== deleteTarget.value.id)
    if (expanded.value === deleteTarget.value.id) expanded.value = null
    deleteTarget.value = null
  } catch (e) {
    alert('삭제 실패: ' + (e.response?.data?.detail || e.message))
  } finally {
    deleting.value = false
  }
}

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function fmtTime(s) {
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
}
function fmtDuration(s) {
  return s >= 60 ? `${Math.floor(s / 60)}분 ${Math.floor(s % 60)}초` : `${Math.floor(s)}초`
}
</script>

<style scoped>
.list-enter-active, .list-leave-active { transition: all 0.3s ease; }
.list-enter-from, .list-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
