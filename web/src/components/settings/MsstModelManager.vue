<template>
  <div class="model-manager">
    <div class="model-manager__header">
      <h3 class="settings-section__title">🎵 人声分离模型</h3>
      <button class="model-manager__refresh" @click="loadModels" :disabled="loading" title="刷新列表">
        🔄
      </button>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="model-manager__loading">加载中...</div>

    <!-- 模型列表 -->
    <div v-else class="model-manager__list">
      <div
        v-for="model in models"
        :key="model.key"
        class="model-card model-card--downloaded"
      >
        <div class="model-card__info">
          <div class="model-card__name">{{ model.name }}</div>
          <div class="model-card__meta">
            <span class="model-card__type">{{ model.model_type }}</span>
            <span class="model-card__size" v-if="model.size_mb > 0">{{ formatSize(model.size_mb) }}</span>
          </div>
        </div>

        <div class="model-card__status">
          <span class="model-card__badge model-card__badge--ok">✓ 可用</span>
        </div>
      </div>

      <div v-if="models.length === 0" class="model-manager__empty">
        没有可用的人声分离模型
      </div>
    </div>

    <!-- 说明 -->
    <div class="model-manager__note">
      <p>人声分离模型用于在歌词对齐前提取纯人声，提高对齐精度。</p>
      <p>模型首次使用时会自动下载，基于 UVR MDX-Net ONNX 模型。</p>
    </div>

    <!-- 提示 -->
    <div v-if="message" class="model-manager__message" :class="messageClass">
      {{ message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { msstApi, type MsstModelItem } from '@/api/client'

const models = ref<MsstModelItem[]>([])
const loading = ref(false)
const message = ref('')
const messageClass = ref('')

onMounted(() => {
  loadModels()
})

async function loadModels() {
  loading.value = true
  message.value = ''
  try {
    const data = await msstApi.list()
    models.value = data.models
  } catch (e: any) {
    message.value = '加载模型列表失败: ' + (e.message || '未知错误')
    messageClass.value = 'model-manager__message--error'
  } finally {
    loading.value = false
  }
}

function formatSize(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(0)} MB`
}
</script>

<style scoped>
.model-manager {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}
.model-manager__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.settings-section__title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  padding-bottom: var(--space-sm);
  border-bottom: 1px solid var(--color-border-light);
  flex: 1;
}
.model-manager__refresh {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--color-btn-secondary);
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}
.model-manager__refresh:hover {
  background: var(--color-accent-soft);
}
.model-manager__refresh:disabled {
  opacity: 0.5;
}

.model-manager__loading {
  text-align: center;
  color: var(--color-text-tertiary);
  padding: var(--space-xl);
}
.model-manager__empty {
  text-align: center;
  color: var(--color-text-tertiary);
  padding: var(--space-lg);
}

.model-manager__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.model-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  padding: var(--space-md);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}
.model-card:hover {
  border-color: var(--color-border);
}
.model-card--downloaded {
  border-left: 3px solid var(--color-success);
}

.model-card__info {
  flex: 1;
  min-width: 0;
}
.model-card__name {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
  margin-bottom: 2px;
}
.model-card__meta {
  display: flex;
  gap: var(--space-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.model-card__type {
  background: var(--color-bg-tertiary);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
}

.model-card__status {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex-shrink: 0;
}

.model-card__badge {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-medium);
}
.model-card__badge--ok {
  background: rgba(52, 199, 89, 0.15);
  color: var(--color-success);
}

.model-manager__note {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  line-height: 1.6;
}

.model-manager__message {
  font-size: var(--font-size-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  text-align: center;
}
.model-manager__message--success {
  background: rgba(52, 199, 89, 0.1);
  color: var(--color-success);
}
.model-manager__message--error {
  background: rgba(255, 59, 48, 0.1);
  color: var(--color-error);
}
</style>
