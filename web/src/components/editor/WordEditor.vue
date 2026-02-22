<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="word-editor-overlay" @click.self="$emit('close')">
        <div class="word-editor">
          <div class="word-editor__header">
            <h3>逐字编辑 — 第 {{ lineIndex + 1 }} 行</h3>
            <button class="word-editor__close" @click="$emit('close')">✕</button>
          </div>

          <div class="word-editor__line-text">{{ lineText }}</div>

          <div class="word-editor__words">
            <div
              v-for="(word, i) in editWords"
              :key="wordKeys[i]"
              class="word-editor__word"
            >
              <div class="word-editor__word-text">{{ word.text }}</div>
              <div class="word-editor__word-times">
                <input
                  type="text"
                  :value="formatMs(word.startTime)"
                  @change="(e) => updateWordTime(i, 'startTime', e)"
                  class="word-editor__time-input"
                  placeholder="开始"
                />
                <span class="word-editor__arrow">→</span>
                <input
                  type="text"
                  :value="formatMs(word.endTime)"
                  @change="(e) => updateWordTime(i, 'endTime', e)"
                  class="word-editor__time-input"
                  placeholder="结束"
                />
              </div>
              <button
                v-if="word.text.length > 1"
                class="word-editor__split-btn"
                @click="splitWord(i)"
                title="拆分为单字"
              >
                ✂️
              </button>
            </div>
          </div>

          <div class="word-editor__footer">
            <button class="word-editor__btn word-editor__btn--cancel" @click="$emit('close')">
              取消
            </button>
            <button class="word-editor__btn word-editor__btn--save" @click="save">
              保存
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { LrcWord } from '@/stores/editorStore'
import { formatMs, parseTime } from '@/utils/time'

const props = defineProps<{
  visible: boolean
  lineIndex: number
  lineText: string
  words: LrcWord[]
}>()

const emit = defineEmits<{
  close: []
  save: [lineIndex: number, words: LrcWord[]]
}>()

const editWords = ref<LrcWord[]>([])
let keyCounter = 0
const wordKeys = ref<number[]>([])

watch(() => props.words, (val) => {
  editWords.value = val.map(w => ({ ...w }))
  wordKeys.value = val.map(() => keyCounter++)
}, { immediate: true })

function updateWordTime(index: number, field: 'startTime' | 'endTime', e: Event) {
  const val = (e.target as HTMLInputElement).value
  editWords.value[index]![field] = parseTime(val)
}

/** 将一个字拆分为单字，时间均分 */
function splitWord(index: number) {
  const word = editWords.value[index]!
  const chars = [...word.text]
  if (chars.length <= 1) return

  const totalDuration = word.endTime - word.startTime
  const charDuration = totalDuration / chars.length

  const newWords: LrcWord[] = chars.map((ch, i) => ({
    text: ch,
    startTime: word.startTime + i * charDuration,
    endTime: word.startTime + (i + 1) * charDuration,
  }))

  // 替换原位置
  editWords.value.splice(index, 1, ...newWords)
  // 更新 keys
  const newKeys = newWords.map(() => keyCounter++)
  wordKeys.value.splice(index, 1, ...newKeys)
}

function save() {
  emit('save', props.lineIndex, editWords.value.map(w => ({ ...w })))
  emit('close')
}
</script>

<style scoped>
.word-editor-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal-backdrop);
  backdrop-filter: blur(4px);
}
.word-editor {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: var(--z-modal);
}
.word-editor__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--color-border-light);
}
.word-editor__header h3 {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
}
.word-editor__close {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--color-btn-secondary);
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.word-editor__close:hover {
  background: var(--color-btn-danger);
  color: white;
}
.word-editor__line-text {
  padding: var(--space-sm) var(--space-lg);
  background: var(--color-bg-secondary);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border-light);
}
.word-editor__words {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-md) var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}
.word-editor__word {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}
.word-editor__word-text {
  min-width: 80px;
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-base);
}
.word-editor__word-times {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  flex: 1;
}
.word-editor__time-input {
  width: 90px;
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-input-bg);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  text-align: center;
}
.word-editor__time-input:focus {
  border-color: var(--color-accent);
  outline: none;
}
.word-editor__arrow {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}
.word-editor__split-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--color-btn-secondary);
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}
.word-editor__split-btn:hover {
  background: var(--color-accent-soft);
  transform: scale(1.1);
}
.word-editor__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--color-border-light);
}
.word-editor__btn {
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  transition: all var(--transition-fast);
}
.word-editor__btn--cancel {
  background: var(--color-btn-secondary);
  color: var(--color-text-secondary);
}
.word-editor__btn--cancel:hover {
  background: var(--color-btn-secondary-hover);
}
.word-editor__btn--save {
  background: var(--color-accent);
  color: white;
}
.word-editor__btn--save:hover {
  background: var(--color-accent-hover);
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-active .word-editor,
.modal-leave-active .word-editor {
  transition: transform 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .word-editor {
  transform: scale(0.95) translateY(10px);
}
.modal-leave-to .word-editor {
  transform: scale(0.95) translateY(10px);
}
</style>
