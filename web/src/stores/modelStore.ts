/**
 * 模型管理 Store
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { modelApi, type ModelItem } from '@/api/client'

export interface DownloadProgress {
    modelKey: string
    progress: number
    message: string
}

export const useModelStore = defineStore('model', () => {
    const models = ref<ModelItem[]>([])
    const loading = ref(false)
    const downloadProgress = ref<Record<string, DownloadProgress>>({})

    async function loadModels() {
        loading.value = true
        try {
            const data = await modelApi.list()
            models.value = data.models
        } finally {
            loading.value = false
        }
    }

    async function downloadModel(key: string, type: string) {
        downloadProgress.value[key] = { modelKey: key, progress: 0, message: '准备下载...' }
        await modelApi.download(key, type)
    }

    async function stopDownload(key: string, type: string) {
        await modelApi.stopDownload(key, type)
        delete downloadProgress.value[key]
    }

    async function deleteModel(key: string, type: string) {
        await modelApi.delete(key, type)
        await loadModels()
    }

    /** 处理 WebSocket 消息 */
    function handleWsMessage(data: any) {
        switch (data.type) {
            case 'download_progress':
                downloadProgress.value[data.model_key] = {
                    modelKey: data.model_key,
                    progress: data.progress,
                    message: data.message,
                }
                break
            case 'download_complete':
                delete downloadProgress.value[data.model_key]
                loadModels()
                break
            case 'download_error':
                delete downloadProgress.value[data.model_key]
                break
        }
    }

    return {
        models, loading, downloadProgress,
        loadModels, downloadModel, stopDownload, deleteModel, handleWsMessage,
    }
})
