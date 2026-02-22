<template>
  <div class="lyrics-input">
    <div class="lyrics-input__header">
      <span class="lyrics-input__title">原始歌词</span>
      <div class="lyrics-input__actions">
        <label class="lyrics-input__upload-btn" title="导入歌词文件">
          📂 导入
          <input
            type="file"
            accept=".lrc,.txt,.srt"
            class="sr-only"
            @change="handleFileImport"
          />
        </label>
        <button
          class="lyrics-input__clear-btn"
          @click="clearText"
          :disabled="!modelValue"
          title="清空"
        >
          🗑️
        </button>
      </div>
    </div>
    <textarea
      class="lyrics-input__textarea"
      :value="modelValue"
      @input="handleInput"
      placeholder="粘贴歌词文本，或导入 LRC/TXT/SRT 文件...&#10;&#10;留空则进行纯语音识别（无歌词对齐）"
      spellcheck="false"
    ></textarea>
  </div>
</template>

<script setup lang="ts">
import { fileApi } from '@/api/client'

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'lyrics-parsed': [data: { rawContent: string; timestamps: number[] }]
  error: [message: string]
}>()

function handleInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLTextAreaElement).value)
}

function clearText() {
  emit('update:modelValue', '')
}

async function handleFileImport(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  try {
    const result = await fileApi.uploadLyrics(file)
    emit('update:modelValue', result.clean_text)
    emit('lyrics-parsed', {
      rawContent: result.raw_content,
      timestamps: result.timestamps,
    })
  } catch (err: any) {
    emit('error', err.message || '歌词导入失败')
  }
  input.value = ''
}
</script>

<style scoped>
.lyrics-input {
  display: flex;
  flex-direction: column;
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.lyrics-input__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-bg-secondary);
}
.lyrics-input__title {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}
.lyrics-input__actions {
  display: flex;
  gap: var(--space-xs);
}
.lyrics-input__upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: var(--color-btn-secondary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.lyrics-input__upload-btn:hover {
  background: var(--color-btn-secondary-hover);
  color: var(--color-text);
}
.lyrics-input__clear-btn {
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: var(--color-btn-secondary);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  transition: background var(--transition-fast);
}
.lyrics-input__clear-btn:hover:not(:disabled) {
  background: var(--color-btn-danger);
  color: white;
}
.lyrics-input__clear-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.lyrics-input__textarea {
  flex: 1;
  min-height: 200px;
  padding: var(--space-md);
  border: none;
  outline: none;
  resize: vertical;
  background: var(--color-input-bg);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  line-height: 1.7;
}
.lyrics-input__textarea::placeholder {
  color: var(--color-text-tertiary);
  font-family: var(--font-sans);
}
</style>
