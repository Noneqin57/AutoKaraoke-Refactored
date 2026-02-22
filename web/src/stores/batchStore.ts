/**
 * 批量处理 Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fileApi, batchApi, type BatchItemRequest } from '@/api/client'

export type BatchItemStatus = 'pending' | 'uploading' | 'running' | 'success' | 'error' | 'aborted'

export interface BatchItem {
    id: string
    audioFile: File | null
    audioFileId: string
    lyricsFile: File | null
    lyricsText: string
    rawContent: string
    name: string
    status: BatchItemStatus
    progress: number
    statusMessage: string
    error: string
}

let nextId = 0

export const useBatchStore = defineStore('batch', () => {
    const items = ref<BatchItem[]>([])
    const isRunning = ref(false)
    const currentIndex = ref(-1)
    const totalItems = ref(0)
    const completedCount = ref(0)

    const hasItems = computed(() => items.value.length > 0)
    const successCount = computed(() => items.value.filter(i => i.status === 'success').length)

    function addPair(audioFile: File, lyricsFile: File) {
        const baseName = audioFile.name.replace(/\.[^/.]+$/, '')
        items.value.push({
            id: `batch_${nextId++}`,
            audioFile,
            audioFileId: '',
            lyricsFile,
            lyricsText: '',
            rawContent: '',
            name: baseName,
            status: 'pending',
            progress: 0,
            statusMessage: '',
            error: '',
        })
    }

    function removeItem(id: string) {
        items.value = items.value.filter(i => i.id !== id)
    }

    function clearAll() {
        items.value = []
        isRunning.value = false
        currentIndex.value = -1
        completedCount.value = 0
    }

    async function startBatch(options: {
        enableForceCalibration: boolean
        enableAvgDistribution: boolean
        enableMsst: boolean
        msstModelKey: string
    }) {
        if (items.value.length === 0) return

        isRunning.value = true
        currentIndex.value = 0
        totalItems.value = items.value.length
        completedCount.value = 0

        // Phase 1: Upload all files
        for (const item of items.value) {
            if (!item.audioFile || !item.lyricsFile) {
                item.status = 'error'
                item.error = '缺少音频或歌词文件'
                continue
            }

            item.status = 'uploading'
            item.statusMessage = '上传中...'

            try {
                // Upload audio
                const audioRes = await fileApi.uploadAudio(item.audioFile)
                item.audioFileId = audioRes.file_id

                // Upload and parse lyrics
                const lyricsRes = await fileApi.uploadLyrics(item.lyricsFile)
                item.lyricsText = lyricsRes.clean_text
                item.rawContent = lyricsRes.raw_content

                item.status = 'pending'
                item.statusMessage = '等待处理...'
            } catch (e: any) {
                item.status = 'error'
                item.error = `上传失败: ${e.message}`
            }
        }

        // Phase 2: Build request and start batch
        const batchItems: BatchItemRequest[] = items.value
            .filter(i => i.status !== 'error')
            .map(i => ({
                audio_file_id: i.audioFileId,
                lyrics_text: i.lyricsText,
                raw_content: i.rawContent,
                name: i.name,
            }))

        if (batchItems.length === 0) {
            isRunning.value = false
            return
        }

        // Mark non-error items as pending
        items.value.forEach(i => {
            if (i.status !== 'error') {
                i.status = 'pending'
                i.statusMessage = '排队中...'
            }
        })

        try {
            await batchApi.start({
                items: batchItems,
                enable_force_calibration: options.enableForceCalibration,
                enable_avg_distribution: options.enableAvgDistribution,
                enable_msst: options.enableMsst,
                msst_model_key: options.msstModelKey,
            })
        } catch (e: any) {
            isRunning.value = false
            items.value.forEach(i => {
                if (i.status === 'pending') {
                    i.status = 'error'
                    i.error = `启动失败: ${e.message}`
                }
            })
        }
    }

    async function stopBatch() {
        try {
            await batchApi.stop()
        } catch {
            // ignore
        }
        isRunning.value = false
    }

    function handleWsMessage(data: any) {
        // Find the matching item by name (non-error items only)
        const validItems = items.value.filter(i => i.status !== 'error' || i.audioFileId)

        switch (data.type) {
            case 'item_start': {
                const idx = data.item_index
                if (idx < validItems.length) {
                    const item = validItems[idx]!
                    item.status = 'running'
                    item.progress = 0
                    item.statusMessage = '开始处理...'
                }
                currentIndex.value = data.item_index
                totalItems.value = data.total
                break
            }
            case 'item_progress': {
                const idx = data.item_index
                if (idx < validItems.length) {
                    validItems[idx]!.progress = data.progress
                }
                break
            }
            case 'item_status': {
                const idx = data.item_index
                if (idx < validItems.length) {
                    validItems[idx]!.statusMessage = data.message
                }
                break
            }
            case 'item_complete': {
                const idx = data.item_index
                if (idx < validItems.length) {
                    const item = validItems[idx]!
                    item.status = data.status === 'success' ? 'success' : 'error'
                    item.progress = data.status === 'success' ? 100 : item.progress
                    item.statusMessage = data.status === 'success' ? '完成' : '失败'
                    if (data.error) item.error = data.error
                }
                completedCount.value++
                break
            }
            case 'batch_complete': {
                isRunning.value = false
                currentIndex.value = -1
                break
            }
        }
    }

    return {
        items, isRunning, currentIndex, totalItems, completedCount,
        hasItems, successCount,
        addPair, removeItem, clearAll, startBatch, stopBatch, handleWsMessage,
    }
})
