<template>
  <div class="mt-8 card p-5">
    <div class="flex items-center gap-2 mb-5">
      <span class="text-xl">🧠</span>
      <h3 class="text-lg font-bold text-gray-100">영상에게 질문하기</h3>
      <span class="text-xs text-gray-600 ml-auto">RAG · ChromaDB · gpt-4o-mini</span>
    </div>

    <!-- 메시지 목록 -->
    <div
      ref="msgBox"
      class="flex flex-col gap-3 mb-4 overflow-y-auto pr-1"
      style="min-height: 80px; max-height: 420px;"
    >
      <p v-if="messages.length === 0" class="text-center text-gray-600 text-sm py-8">
        이 영상 내용에 대해 무엇이든 물어보세요 💬
      </p>

      <template v-for="(msg, i) in messages" :key="i">
        <!-- 사용자 -->
        <div v-if="msg.role === 'user'" class="flex justify-end">
          <div class="bg-brand-600 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm max-w-xs leading-relaxed">
            {{ msg.content }}
          </div>
        </div>

        <!-- AI 답변 -->
        <div v-else class="flex justify-start gap-2">
          <div class="w-7 h-7 rounded-full bg-purple-900/60 flex items-center justify-center text-sm shrink-0 mt-0.5">🤖</div>
          <div class="bg-gray-800 rounded-2xl rounded-tl-sm px-4 py-3 text-sm max-w-sm">
            <p class="text-gray-200 whitespace-pre-wrap leading-relaxed">{{ msg.content }}</p>
            <!-- 출처 타임스탬프 -->
            <div v-if="msg.sources?.length" class="mt-2.5 flex flex-wrap gap-1.5">
              <span
                v-for="(src, j) in msg.sources"
                :key="j"
                class="text-xs bg-purple-950/60 text-purple-300 px-2.5 py-1 rounded-full border border-purple-800/40 cursor-default"
                :title="src.preview"
              >
                📍 {{ fmtTime(src.start) }}
              </span>
            </div>
          </div>
        </div>
      </template>

      <!-- 로딩 -->
      <div v-if="loading" class="flex justify-start gap-2">
        <div class="w-7 h-7 rounded-full bg-purple-900/60 flex items-center justify-center text-sm shrink-0">🤖</div>
        <div class="bg-gray-800 rounded-2xl rounded-tl-sm px-4 py-3">
          <span class="text-gray-500 text-sm">생각 중</span>
          <span class="text-gray-500 text-sm animate-pulse">...</span>
        </div>
      </div>
    </div>

    <!-- 예시 질문 (첫 메시지 전) -->
    <div v-if="messages.length === 0" class="flex flex-wrap gap-2 mb-3">
      <button
        v-for="q in exampleQuestions"
        :key="q"
        class="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-full transition-colors"
        @click="sendQuestion(q)"
      >
        {{ q }}
      </button>
    </div>

    <!-- 입력창 -->
    <div class="flex gap-2">
      <input
        v-model="input"
        @keydown.enter="sendQuestion(input)"
        :disabled="loading"
        type="text"
        placeholder="이 영상의 핵심 내용이 뭐야?"
        class="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200
               placeholder-gray-600 focus:outline-none focus:border-purple-600 disabled:opacity-50 transition-colors"
      />
      <button
        @click="sendQuestion(input)"
        :disabled="loading || !input.trim()"
        class="bg-brand-600 hover:bg-brand-700 disabled:opacity-40 text-white px-4 py-2.5
               rounded-xl text-sm font-medium transition-colors shrink-0"
      >
        전송
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'

const props = defineProps({
  jobId: { type: String, required: true },
})

const input = ref('')
const messages = ref([])
const loading = ref(false)
const msgBox = ref(null)

const exampleQuestions = [
  '이 영상의 핵심 내용 요약해줘',
  '어떤 나라 얘기야?',
  '가장 흥미로운 사실이 뭐야?',
]

async function sendQuestion(q) {
  q = (q || '').trim()
  if (!q || loading.value) return

  messages.value.push({ role: 'user', content: q })
  input.value = ''
  loading.value = true
  await scrollBottom()

  try {
    const res = await fetch(`/api/jobs/${props.jobId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '오류')
    messages.value.push({ role: 'assistant', content: data.answer, sources: data.sources })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: `오류: ${e.message}`, sources: [] })
  } finally {
    loading.value = false
    await scrollBottom()
  }
}

async function scrollBottom() {
  await nextTick()
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
}

function fmtTime(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>
