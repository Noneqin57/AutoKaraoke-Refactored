/**
 * 主题切换组合式函数
 */
import { ref, watchEffect } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'reatk-theme'

// 全局响应式状态
const theme = ref<ThemeMode>(loadTheme())

function loadTheme(): ThemeMode {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode
    if (saved === 'light' || saved === 'dark') return saved
    // 跟随系统
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useTheme() {
    // 监听变化并应用到 DOM
    watchEffect(() => {
        document.documentElement.setAttribute('data-theme', theme.value)
        localStorage.setItem(STORAGE_KEY, theme.value)
    })

    function toggleTheme() {
        theme.value = theme.value === 'light' ? 'dark' : 'light'
    }

    function setTheme(mode: ThemeMode) {
        theme.value = mode
    }

    return {
        theme,
        toggleTheme,
        setTheme,
        isDark: () => theme.value === 'dark',
    }
}
