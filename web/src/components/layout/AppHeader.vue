<template>
  <header class="app-header">
    <div class="app-header__left">
      <router-link to="/" class="app-header__logo">
        <span class="app-header__logo-icon">🎤</span>
        <span class="app-header__logo-text">REATK</span>
      </router-link>
    </div>

    <nav class="app-header__nav">
      <router-link to="/" class="app-header__nav-item" active-class="active">
        生成
      </router-link>
      <router-link to="/editor" class="app-header__nav-item" active-class="active">
        逐行编辑
      </router-link>
      <router-link to="/editor/word" class="app-header__nav-item" active-class="active">
        逐字编辑
      </router-link>
      <router-link to="/batch" class="app-header__nav-item" active-class="active">
        批量生成
      </router-link>
      <router-link to="/settings" class="app-header__nav-item" active-class="active">
        设置
      </router-link>
    </nav>

    <div class="app-header__right">
      <ThemeToggle />
    </div>
  </header>
</template>

<script setup lang="ts">
import ThemeToggle from './ThemeToggle.vue'
</script>

<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: var(--z-dropdown);
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--space-lg);
  background: var(--color-header-bg);
  border-bottom: 1px solid var(--color-header-border);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.app-header__left {
  flex-shrink: 0;
}

.app-header__logo {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  text-decoration: none;
  color: var(--color-text);
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-lg);
}
.app-header__logo:hover {
  text-decoration: none;
}
.app-header__logo-icon {
  font-size: 24px;
}

.app-header__nav {
  display: flex;
  gap: var(--space-xs);
}

.app-header__nav-item {
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-sm);
  text-decoration: none;
  transition: all var(--transition-fast);
}
.app-header__nav-item:hover {
  color: var(--color-text);
  background: var(--color-bg-tertiary);
  text-decoration: none;
}
.app-header__nav-item.active {
  color: var(--color-text);
  background: var(--color-accent-soft);
}

.app-header__right {
  flex-shrink: 0;
}
</style>
