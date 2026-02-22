<template>
  <div class="status-bar" :class="{ 'status-bar--active': isActive }">
    <!-- 进度条 -->
    <div class="status-bar__progress-track">
      <div
        class="status-bar__progress-fill"
        :class="statusClass"
        :style="{ width: progress + '%' }"
      ></div>
    </div>

    <div class="status-bar__content">
      <!-- 状态消息 -->
      <div class="status-bar__message">
        <span class="status-bar__indicator" :class="statusClass"></span>
        <span>{{ message || '就绪' }}</span>
      </div>

      <!-- 右侧操作 -->
      <div class="status-bar__actions" v-if="hasResult">
        <select
          class="status-bar__encoding"
          v-model="encoding"
          title="编码"
        >
          <option value="utf-8">UTF-8</option>
          <option value="utf-8-sig">UTF-8 BOM</option>
          <option value="gbk">GBK</option>
          <option value="big5">Big5</option>
        </select>
        <button
          class="status-bar__save-btn"
          @click="$emit('save')"
          title="保存文件"
        >
          💾 保存
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: 'idle' | 'running' | 'success' | 'error' | 'aborted'
  message: string
  progress: number
  hasResult: boolean
}>()

defineEmits<{
  save: []
}>()

const encoding = defineModel<string>('encoding', { default: 'utf-8' })

const isActive = computed(() => props.status === 'running')

const statusClass = computed(() => ({
  'status-bar--running': props.status === 'running',
  'status-bar--success': props.status === 'success',
  'status-bar--error': props.status === 'error',
  'status-bar--aborted': props.status === 'aborted',
}))
</script>

<style scoped>
.status-bar {
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.status-bar__progress-track {
  height: 3px;
  background: var(--color-progress-bg);
}
.status-bar__progress-fill {
  height: 100%;
  transition: width 0.3s ease;
  border-radius: 0 2px 2px 0;
}
.status-bar__progress-fill.status-bar--running {
  background: var(--color-accent);
  animation: pulse-glow 2s ease-in-out infinite;
}
.status-bar__progress-fill.status-bar--success {
  background: var(--color-success);
}
.status-bar__progress-fill.status-bar--error {
  background: var(--color-error);
}
.status-bar__progress-fill.status-bar--aborted {
  background: var(--color-warning);
}
.status-bar__content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm) var(--space-md);
}
.status-bar__message {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}
.status-bar__indicator {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--color-text-tertiary);
  flex-shrink: 0;
}
.status-bar__indicator.status-bar--running {
  background: var(--color-accent);
  animation: blink 1s ease-in-out infinite;
}
.status-bar__indicator.status-bar--success { background: var(--color-success); }
.status-bar__indicator.status-bar--error { background: var(--color-error); }
.status-bar__indicator.status-bar--aborted { background: var(--color-warning); }
.status-bar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.status-bar__encoding {
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-input-bg);
  color: var(--color-text);
  font-size: var(--font-size-xs);
  outline: none;
}
.status-bar__encoding:focus {
  border-color: var(--color-accent);
}
.status-bar__save-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  background: var(--color-accent);
  color: white;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  transition: all var(--transition-fast);
}
.status-bar__save-btn:hover {
  background: var(--color-accent-hover);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
@keyframes pulse-glow {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
</style>
