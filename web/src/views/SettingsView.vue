<template>
  <div class="settings-view">
    <div class="settings-view__container">
      <!-- 侧边导航 -->
      <nav class="settings-view__nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="settings-view__nav-btn"
          :class="{ 'settings-view__nav-btn--active': activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span class="settings-view__nav-icon">{{ tab.icon }}</span>
          {{ tab.label }}
        </button>
      </nav>

      <!-- 内容区 -->
      <div class="settings-view__content">
        <CoreSettings v-show="activeTab === 'core'" />
        <PathSettings v-show="activeTab === 'paths'" />
        <ModelManager v-show="activeTab === 'models'" />
        <MsstModelManager v-show="activeTab === 'msst'" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'SettingsView' })
import { ref, onMounted } from 'vue'
import CoreSettings from '@/components/settings/CoreSettings.vue'
import PathSettings from '@/components/settings/PathSettings.vue'
import ModelManager from '@/components/settings/ModelManager.vue'
import MsstModelManager from '@/components/settings/MsstModelManager.vue'
import { useConfigStore } from '@/stores/configStore'

const configStore = useConfigStore()
const activeTab = ref('core')

const tabs = [
  { key: 'core', icon: '🎤', label: '核心设置' },
  { key: 'paths', icon: '📁', label: '路径设置' },
  { key: 'models', icon: '🧠', label: '模型管理' },
  { key: 'msst', icon: '🎵', label: '人声分离' },
]

onMounted(async () => {
  // 确保配置和语言列表已加载
  if (Object.keys(configStore.config).length === 0) {
    try {
      await configStore.loadConfig()
      await configStore.loadLanguages()
    } catch {
      // 后端未连接时静默
    }
  }
})
</script>

<style scoped>
.settings-view {
  flex: 1;
  display: flex;
  justify-content: center;
  padding: var(--space-lg);
}
.settings-view__container {
  display: flex;
  gap: var(--space-lg);
  width: 100%;
  max-width: 960px;
}

/* 侧边导航 */
.settings-view__nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  min-width: 160px;
  flex-shrink: 0;
}
.settings-view__nav-btn {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  text-align: left;
  transition: all var(--transition-fast);
  cursor: pointer;
}
.settings-view__nav-btn:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text);
}
.settings-view__nav-btn--active {
  background: var(--color-accent-soft);
  color: var(--color-accent);
  font-weight: var(--font-weight-semibold);
}
.settings-view__nav-icon {
  font-size: 16px;
}

/* 内容区 */
.settings-view__content {
  flex: 1;
  min-width: 0;
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-xl);
  padding: var(--space-xl);
}

/* 响应式：小屏幕改为上下布局 */
@media (max-width: 640px) {
  .settings-view__container {
    flex-direction: column;
  }
  .settings-view__nav {
    flex-direction: row;
    min-width: unset;
    overflow-x: auto;
  }
  .settings-view__nav-btn {
    white-space: nowrap;
  }
}
</style>
