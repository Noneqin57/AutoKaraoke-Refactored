<template>
  <div class="gen-controls">
    <div class="gen-controls__options">
      <label class="gen-controls__check">
        <input type="checkbox" v-model="forceCalibration" />
        <span>强制校准</span>
      </label>
      <label class="gen-controls__check">
        <input type="checkbox" v-model="avgDistribution" />
        <span>均匀分配</span>
      </label>

      <div class="gen-controls__separator"></div>

      <label class="gen-controls__check">
        <input type="checkbox" v-model="enableMsst" />
        <span>人声分离</span>
      </label>
      <select
        v-if="enableMsst"
        class="gen-controls__msst-select"
        v-model="msstModelKey"
      >
        <option v-for="model in msstModels" :key="model.key" :value="model.key">
          {{ model.name }}
        </option>
      </select>
    </div>
    <div class="gen-controls__buttons">
      <button
        v-if="!isRunning"
        class="gen-controls__btn gen-controls__btn--primary"
        :disabled="!canStart"
        @click="$emit('start')"
      >
        <span class="gen-controls__btn-icon">▶</span>
        开始生成
      </button>
      <button
        v-else
        class="gen-controls__btn gen-controls__btn--danger"
        @click="$emit('stop')"
      >
        <span class="gen-controls__btn-icon">■</span>
        停止
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MsstModelItem } from '@/api/client'

const props = defineProps<{
  isRunning: boolean
  hasAudio: boolean
  msstModels: MsstModelItem[]
}>()

defineEmits<{
  start: []
  stop: []
}>()

const forceCalibration = defineModel<boolean>('forceCalibration', { default: true })
const avgDistribution = defineModel<boolean>('avgDistribution', { default: false })
const enableMsst = defineModel<boolean>('enableMsst', { default: false })
const msstModelKey = defineModel<string>('msstModelKey', { default: '' })

const canStart = computed(() => props.hasAudio && !props.isRunning)
</script>

<style scoped>
.gen-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
}
.gen-controls__options {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  flex-wrap: wrap;
}
.gen-controls__check {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
  user-select: none;
}
.gen-controls__check input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-accent);
  cursor: pointer;
}
.gen-controls__check span {
  transition: color var(--transition-fast);
}
.gen-controls__check:hover span {
  color: var(--color-text);
}
.gen-controls__separator {
  width: 1px;
  height: 20px;
  background: var(--color-border-light);
}
.gen-controls__msst-select {
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-input-bg);
  color: var(--color-text);
  font-size: var(--font-size-xs);
  cursor: pointer;
}
.gen-controls__msst-select:focus {
  border-color: var(--color-accent);
  outline: none;
}
.gen-controls__buttons {
  display: flex;
  gap: var(--space-sm);
}
.gen-controls__btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  transition: all var(--transition-fast);
}
.gen-controls__btn--primary {
  background: var(--color-btn-primary);
  color: white;
}
.gen-controls__btn--primary:hover:not(:disabled) {
  background: var(--color-btn-primary-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}
.gen-controls__btn--primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.gen-controls__btn--danger {
  background: var(--color-btn-danger);
  color: white;
}
.gen-controls__btn--danger:hover {
  background: var(--color-btn-danger-hover);
}
.gen-controls__btn-icon {
  font-size: 12px;
}
</style>
