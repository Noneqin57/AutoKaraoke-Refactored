<template>
  <div class="karaoke-preview">
    <div class="karaoke-preview__container">
      <!-- 前一行 -->
      <div class="karaoke-preview__line karaoke-preview__line--prev" v-if="prevLine">
        {{ prevLine.text }}
      </div>

      <!-- 当前行（逐字高亮） -->
      <div class="karaoke-preview__line karaoke-preview__line--current" v-if="currentLine">
        <span
          v-for="(word, i) in currentWords"
          :key="i"
          class="karaoke-preview__word"
          :class="{
            'karaoke-preview__word--sung': word.progress >= 1,
            'karaoke-preview__word--active': word.progress > 0 && word.progress < 1,
          }"
          :style="word.progress > 0 && word.progress < 1
            ? { '--progress': word.progress }
            : {}
          "
        >{{ word.text }}</span>
      </div>
      <div class="karaoke-preview__line karaoke-preview__line--empty" v-else>
        ♪ 等待播放 ♪
      </div>

      <!-- 下一行 -->
      <div class="karaoke-preview__line karaoke-preview__line--next" v-if="nextLine">
        {{ nextLine.text }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { LrcLine } from '@/stores/editorStore'

const props = defineProps<{
  lines: LrcLine[]
  currentTime: number
}>()

/** 节流后的当前时间 (每 ~66ms 更新一次，约 15fps，足够卡拉OK显示) */
const throttledTime = ref(0)
let rafPending = false

watch(() => props.currentTime, (newTime) => {
  if (!rafPending) {
    rafPending = true
    requestAnimationFrame(() => {
      throttledTime.value = newTime
      rafPending = false
    })
  }
})

/** 找到当前行索引 */
const currentLineIndex = computed(() => {
  const t = throttledTime.value
  for (let i = props.lines.length - 1; i >= 0; i--) {
    if (t >= props.lines[i]!.startTime) return i
  }
  return -1
})

const currentLine = computed(() =>
  currentLineIndex.value >= 0 ? props.lines[currentLineIndex.value] : null
)
const prevLine = computed(() =>
  currentLineIndex.value > 0 ? props.lines[currentLineIndex.value - 1] : null
)
const nextLine = computed(() =>
  currentLineIndex.value >= 0 && currentLineIndex.value < props.lines.length - 1
    ? props.lines[currentLineIndex.value + 1]
    : null
)

/** 计算每个字的进度 */
const currentWords = computed(() => {
  const line = currentLine.value
  if (!line) return []
  const t = throttledTime.value

  if (line.words.length > 0) {
    return line.words.map(w => ({
      text: w.text,
      progress: t <= w.startTime ? 0
        : t >= w.endTime ? 1
        : (t - w.startTime) / (w.endTime - w.startTime)
    }))
  }

  // 没有逐字数据时，整行按比例填充
  const lineProgress = line.endTime > line.startTime
    ? Math.max(0, Math.min(1, (t - line.startTime) / (line.endTime - line.startTime)))
    : 0
  return [{ text: line.text, progress: lineProgress }]
})
</script>

<style scoped>
.karaoke-preview {
  background: var(--color-karaoke-bg);
  border-radius: var(--radius-lg);
  padding: var(--space-xl) var(--space-lg);
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.karaoke-preview__container {
  text-align: center;
  width: 100%;
}
.karaoke-preview__line {
  padding: var(--space-xs) 0;
  transition: opacity var(--transition-base);
  white-space: pre-wrap;
  word-break: break-word;
}
.karaoke-preview__line--prev {
  font-size: var(--font-size-sm);
  color: var(--color-karaoke-unsung);
  opacity: 0.5;
}
.karaoke-preview__line--current {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-karaoke-unsung);
  margin: var(--space-sm) 0;
}
.karaoke-preview__line--next {
  font-size: var(--font-size-sm);
  color: var(--color-karaoke-unsung);
  opacity: 0.4;
}
.karaoke-preview__line--empty {
  font-size: var(--font-size-lg);
  color: var(--color-karaoke-unsung);
  opacity: 0.3;
}

/* 逐字高亮 */
.karaoke-preview__word--sung {
  color: var(--color-karaoke-sung);
}
.karaoke-preview__word--active {
  background: linear-gradient(
    to right,
    var(--color-karaoke-active) calc(var(--progress, 0) * 100%),
    var(--color-karaoke-unsung) calc(var(--progress, 0) * 100%)
  );
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
</style>
