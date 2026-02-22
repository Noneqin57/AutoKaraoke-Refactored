<template>
  <button class="theme-toggle" @click="toggleTheme" :title="isDark() ? '切换到浅色' : '切换到深色'">
    <span class="theme-toggle__icon">{{ isDark() ? '☀️' : '🌙' }}</span>
  </button>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'

const { toggleTheme, isDark } = useTheme()
</script>

<style scoped>
.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--color-btn-secondary);
  color: var(--color-text);
  transition: background var(--transition-fast), transform var(--transition-fast);
}
.theme-toggle:hover {
  background: var(--color-btn-secondary-hover);
  transform: scale(1.1);
}
.theme-toggle__icon {
  font-size: 18px;
  line-height: 1;
}
</style>
