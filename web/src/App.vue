<template>
  <div class="app" :data-theme="theme">
    <AppHeader />
    <main class="app__content">
      <router-view v-slot="{ Component }">
        <keep-alive include="MainView,SettingsView">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import { useTheme } from '@/composables/useTheme'
import { useConfigStore } from '@/stores/configStore'

const { theme } = useTheme()
const configStore = useConfigStore()

onMounted(async () => {
  // 初始化加载配置
  try {
    await configStore.loadConfig()
    await configStore.loadLanguages()
  } catch (e) {
    console.warn('后端未连接，部分功能不可用', e)
  }
})
</script>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.app__content {
  flex: 1;
  display: flex;
  flex-direction: column;
}
</style>
