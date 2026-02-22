<template>
  <div class="model-manager">
    <div class="model-manager__header">
      <h3 class="settings-section__title">🧠 模型管理</h3>
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
        :key="model.key + model.type"
        class="model-card"
        :class="{ 'model-card--downloaded': model.is_downloaded }"
      >
        <div class="model-card__info">
          <div class="model-card__name">{{ model.name }}</div>
          <div class="model-card__meta">
            <span class="model-card__type">{{ model.type }}</span>
            <span class="model-card__size" v-if="model.size_mb > 0">{{ formatSize(model.size_mb) }}</span>
          </div>
        </div>

        <div class="model-card__status">
          <!-- 已下载 -->
          <template v-if="model.is_downloaded">
            <span class="model-card__badge model-card__badge--ok">✓ 已下载</span>
            <button
              class="model-card__action model-card__action--delete"
              @click="deleteModel(model)"
              :disabled="deletingKeys.has(model.key)"
              title="删除模型"
            >
              🗑️
            </button>
          </template>

          <!-- 下载中 -->
          <template v-else-if="downloadProgress[model.key] !== undefined">
            <div class="model-card__progress">
              <div class="model-card__progress-bar">
                <div
                  class="model-card__progress-fill"
                  :style="{ width: downloadProgress[model.key] + '%' }"
                ></div>
              </div>
              <span class="model-card__progress-text">{{ downloadProgress[model.key] }}%</span>
            </div>
            <button
              class="model-card__action model-card__action--stop"
              @click="stopDownload(model)"
              title="停止下载"
            >
              ⏹
            </button>
          </template>

          <!-- 未下载 -->
          <template v-else>
            <button
              class="model-card__action model-card__action--download"
              @click="startDownload(model)"
              title="下载模型"
            >
              ⬇️ 下载
            </button>
          </template>
        </div>
      </div>

      <div v-if="models.length === 0" class="model-manager__empty">
        没有可用的模型信息
      </div>
    </div>

    <!-- 提示 -->
    <div v-if="message" class="model-manager__message" :class="messageClass">
      {{ message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { modelApi, type ModelItem } from '@/api/client'

const models = ref<ModelItem[]>([])
const loading = ref(false)
const message = ref('')
const messageClass = ref('')
const downloadProgress = ref<Record<string, number>>({})
const deletingKeys = ref(new Set<string>())

let ws: WebSocket | null = null
let wsReconnectCount = 0
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null
const WS_MAX_RECONNECTS = 10

onMounted(() => {
  loadModels()
  connectWs()
})

onUnmounted(() => {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  ws?.close()
})

async function loadModels() {
  loading.value = true
  message.value = ''
  try {
    const data = await modelApi.list()
    models.value = data.models
  } catch (e: any) {
    message.value = '加载模型列表失败: ' + (e.message || '未知错误')
    messageClass.value = 'model-manager__message--error'
  } finally {
    loading.value = false
  }
}

function connectWs() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${location.host}/api/model/ws`
  ws = new WebSocket(wsUrl)

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'download_progress') {
        downloadProgress.value[data.model_key] = data.progress
      } else if (data.type === 'download_complete') {
        delete downloadProgress.value[data.model_key]
        message.value = `模型 ${data.model_key} 下载完成`
        messageClass.value = 'model-manager__message--success'
        loadModels()
      } else if (data.type === 'download_error') {
        delete downloadProgress.value[data.model_key]
        message.value = `下载失败: ${data.message}`
        messageClass.value = 'model-manager__message--error'
      }
    } catch { /* ignore parse errors */ }
  }

  ws.onclose = () => {
    // 带最大重试次数的自动重连
    if (wsReconnectCount < WS_MAX_RECONNECTS) {
      wsReconnectTimer = setTimeout(() => {
        wsReconnectTimer = null
        if (!ws || ws.readyState === WebSocket.CLOSED) {
          wsReconnectCount++
          connectWs()
        }
      }, 3000)
    }
  }
}

async function startDownload(model: ModelItem) {
  // 防止重复点击
  if (downloadProgress.value[model.key] !== undefined) return
  message.value = ''
  downloadProgress.value[model.key] = 0
  try {
    await modelApi.download(model.key, model.type)
  } catch (e: any) {
    delete downloadProgress.value[model.key]
    message.value = e.message || '下载启动失败'
    messageClass.value = 'model-manager__message--error'
  }
}

async function stopDownload(model: ModelItem) {
  try {
    await modelApi.stopDownload(model.key, model.type)
    delete downloadProgress.value[model.key]
  } catch (e: any) {
    message.value = e.message || '停止失败'
    messageClass.value = 'model-manager__message--error'
  }
}

async function deleteModel(model: ModelItem) {
  if (!confirm(`确定删除模型 "${model.name}" 吗？此操作不可撤销。`)) return
  deletingKeys.value.add(model.key)
  try {
    await modelApi.delete(model.key, model.type)
    message.value = `已删除模型 ${model.name}`
    messageClass.value = 'model-manager__message--success'
    await loadModels()
  } catch (e: any) {
    message.value = e.message || '删除失败'
    messageClass.value = 'model-manager__message--error'
  } finally {
    deletingKeys.value.delete(model.key)
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

.model-card__progress {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  min-width: 120px;
}
.model-card__progress-bar {
  flex: 1;
  height: 6px;
  background: var(--color-progress-bg);
  border-radius: 3px;
  overflow: hidden;
}
.model-card__progress-fill {
  height: 100%;
  background: var(--color-accent);
  border-radius: 3px;
  transition: width 0.3s ease;
}
.model-card__progress-text {
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
  min-width: 36px;
  text-align: right;
}

.model-card__action {
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  gap: 4px;
}
.model-card__action--download {
  background: var(--color-accent);
  color: white;
}
.model-card__action--download:hover {
  background: var(--color-accent-hover);
}
.model-card__action--stop {
  background: var(--color-btn-secondary);
}
.model-card__action--stop:hover {
  background: var(--color-warning);
  color: white;
}
.model-card__action--delete {
  background: transparent;
  font-size: 14px;
}
.model-card__action--delete:hover {
  background: var(--color-btn-danger);
  color: white;
}
.model-card__action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
