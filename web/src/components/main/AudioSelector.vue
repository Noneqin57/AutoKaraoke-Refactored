<template>
  <div
    class="audio-selector"
    :class="{ 'audio-selector--drag-over': isDragOver, 'audio-selector--has-file': hasFile }"
    @dragover.prevent="isDragOver = true"
    @dragleave="isDragOver = false"
    @drop.prevent="handleDrop"
  >
    <div v-if="!hasFile" class="audio-selector__empty" @click="openPicker">
      <div class="audio-selector__icon">🎵</div>
      <div class="audio-selector__label">拖拽音频文件到这里</div>
      <div class="audio-selector__hint">或点击选择文件</div>
      <div class="audio-selector__formats">支持 MP3 / WAV / FLAC / M4A / OGG / AAC</div>
    </div>

    <div v-else class="audio-selector__file">
      <div class="audio-selector__file-icon">🎵</div>
      <div class="audio-selector__file-info">
        <div class="audio-selector__file-name">{{ filename }}</div>
        <div class="audio-selector__file-size">{{ formattedSize }}</div>
      </div>
      <button class="audio-selector__change" @click="openPicker" title="更换文件">
        🔄
      </button>
      <button class="audio-selector__remove" @click="removeFile" title="移除">
        ✕
      </button>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept=".mp3,.wav,.flac,.m4a,.ogg,.aac,.wma"
      class="audio-selector__input"
      @change="handleFileSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { fileApi } from '@/api/client'
import { useAudioStore } from '@/stores/audioStore'

const emit = defineEmits<{
  uploaded: [fileId: string]
  removed: []
  error: [message: string]
}>()

const audioStore = useAudioStore()
const fileInput = ref<HTMLInputElement>()
const isDragOver = ref(false)
const uploading = ref(false)

const hasFile = computed(() => !!audioStore.fileId)
const filename = computed(() => audioStore.filename)
const formattedSize = computed(() => {
  const mb = audioStore.fileSize / (1024 * 1024)
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${(audioStore.fileSize / 1024).toFixed(0)} KB`
})

function openPicker() {
  fileInput.value?.click()
}

async function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) await uploadFile(file)
  input.value = ''
}

function handleDrop(e: DragEvent) {
  isDragOver.value = false
  const file = e.dataTransfer?.files[0]
  if (file) uploadFile(file)
}

async function uploadFile(file: File) {
  if (uploading.value) return
  uploading.value = true
  try {
    const res = await fileApi.uploadAudio(file)
    audioStore.setFile(res.file_id, res.filename, res.size)
    emit('uploaded', res.file_id)
  } catch (e: any) {
    emit('error', e.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

function removeFile() {
  audioStore.reset()
  emit('removed')
}
</script>

<style scoped>
.audio-selector {
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-lg);
  transition: all var(--transition-base);
  overflow: hidden;
}
.audio-selector--drag-over {
  border-color: var(--color-accent);
  background: var(--color-accent-soft);
}
.audio-selector__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-xl) var(--space-lg);
  cursor: pointer;
  user-select: none;
}
.audio-selector__empty:hover {
  background: var(--color-bg-secondary);
}
.audio-selector__icon {
  font-size: 40px;
  margin-bottom: var(--space-sm);
}
.audio-selector__label {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  margin-bottom: var(--space-xs);
}
.audio-selector__hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-sm);
}
.audio-selector__formats {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.audio-selector__file {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  background: var(--color-bg-secondary);
}
.audio-selector__file-icon {
  font-size: 28px;
  flex-shrink: 0;
}
.audio-selector__file-info {
  flex: 1;
  min-width: 0;
}
.audio-selector__file-name {
  font-weight: var(--font-weight-medium);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.audio-selector__file-size {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}
.audio-selector__change,
.audio-selector__remove {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--color-btn-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: background var(--transition-fast);
}
.audio-selector__change:hover { background: var(--color-btn-secondary-hover); }
.audio-selector__remove:hover { background: var(--color-btn-danger); color: white; }
.audio-selector__input {
  display: none;
}
.audio-selector--has-file {
  border-style: solid;
  border-color: var(--color-border-light);
}
</style>
