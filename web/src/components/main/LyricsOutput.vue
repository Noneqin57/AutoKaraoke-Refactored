<template>
  <div class="lyrics-output">
    <div class="lyrics-output__header">
      <span class="lyrics-output__title">生成结果</span>
      <div class="lyrics-output__actions" v-if="modelValue">
        <button class="lyrics-output__btn" @click="copyToClipboard" title="复制">
          📋 复制
        </button>
        <button class="lyrics-output__btn" @click="$emit('edit')" title="编辑器">
          ✏️ 编辑
        </button>
      </div>
    </div>
    <textarea
      class="lyrics-output__textarea"
      :value="modelValue"
      readonly
      placeholder="生成的逐字歌词将显示在这里..."
    ></textarea>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string
}>()

defineEmits<{
  edit: []
}>()

async function copyToClipboard() {
  try {
    // The prop is available via the template, but we need to access it in script
    const textarea = document.querySelector('.lyrics-output__textarea') as HTMLTextAreaElement
    if (textarea?.value) {
      await navigator.clipboard.writeText(textarea.value)
    }
  } catch {
    // fallback
  }
}
</script>

<style scoped>
.lyrics-output {
  display: flex;
  flex-direction: column;
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.lyrics-output__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-bg-secondary);
}
.lyrics-output__title {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}
.lyrics-output__actions {
  display: flex;
  gap: var(--space-xs);
}
.lyrics-output__btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: var(--color-btn-secondary);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  transition: all var(--transition-fast);
}
.lyrics-output__btn:hover {
  background: var(--color-btn-secondary-hover);
  color: var(--color-text);
}
.lyrics-output__textarea {
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
  cursor: default;
}
.lyrics-output__textarea::placeholder {
  color: var(--color-text-tertiary);
  font-family: var(--font-sans);
}
</style>
