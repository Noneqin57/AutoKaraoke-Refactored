/**
 * 配置 Store
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { configApi, type LanguageItem } from '@/api/client'

export const useConfigStore = defineStore('config', () => {
    const config = ref<Record<string, any>>({})
    const languages = ref<LanguageItem[]>([])
    const promptDefaults = ref<Record<string, string>>({})
    const loading = ref(false)

    async function loadConfig() {
        loading.value = true
        try {
            const data = await configApi.get()
            config.value = data.config
        } finally {
            loading.value = false
        }
    }

    async function updateConfig(updates: Record<string, any>) {
        const data = await configApi.update(updates)
        config.value = data.config
    }

    async function loadLanguages() {
        const data = await configApi.getLanguages()
        languages.value = data.languages
    }

    async function loadPromptDefaults() {
        promptDefaults.value = await configApi.getPromptDefaults()
    }

    function get(key: string, defaultValue: any = null) {
        return config.value[key] ?? defaultValue
    }

    return {
        config, languages, promptDefaults, loading,
        loadConfig, updateConfig, loadLanguages, loadPromptDefaults, get,
    }
})
