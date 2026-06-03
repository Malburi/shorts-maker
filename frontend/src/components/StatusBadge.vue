<template>
  <span
    class="text-xs font-semibold px-3 py-1 rounded-full"
    :class="styles[status] ?? styles.pending"
  >
    {{ labels[status] ?? status }}
  </span>
</template>

<script setup>
defineProps({ status: String })

const labels = {
  pending: '대기 중',
  processing: '처리 중',
  done: '완료',
  error: '오류',
}
const styles = {
  pending:    'bg-gray-700 text-gray-300',
  processing: 'bg-yellow-900/60 text-yellow-300 animate-pulse',
  done:       'bg-green-900/60 text-green-300',
  error:      'bg-red-900/60 text-red-300',
}
</script>
