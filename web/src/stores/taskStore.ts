/**
 * 生成任务 Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { taskApi, type TaskStartRequest } from '@/api/client'

export type TaskStatus = 'idle' | 'running' | 'success' | 'error' | 'aborted'

export const useTaskStore = defineStore('task', () => {
    const status = ref<TaskStatus>('idle')
    const statusMessage = ref('')
    const progress = ref(0)
    const result = ref('')
    const error = ref('')

    const isRunning = computed(() => status.value === 'running')

    async function startTask(req: TaskStartRequest) {
        // 先重置状态，但不设 running —— 等 API 成功后再设
        statusMessage.value = '正在启动...'
        progress.value = 0
        result.value = ''
        error.value = ''

        try {
            await taskApi.start(req)
            // API 成功后才设为 running
            status.value = 'running'
        } catch (e: any) {
            status.value = 'error'
            error.value = e.message
        }
    }

    async function stopTask() {
        try {
            await taskApi.stop()
            statusMessage.value = '正在停止...'
        } catch (e: any) {
            error.value = e.message
        }
    }

    /** 处理 WebSocket 消息 */
    function handleWsMessage(data: any) {
        switch (data.type) {
            case 'progress':
                progress.value = data.progress
                break
            case 'status':
                statusMessage.value = data.message
                break
            case 'result':
                status.value = 'success'
                result.value = data.result
                statusMessage.value = '生成完成！'
                progress.value = 100
                break
            case 'error':
                status.value = 'error'
                error.value = data.message
                statusMessage.value = '发生错误'
                break
            case 'aborted':
                status.value = 'aborted'
                statusMessage.value = '已中止'
                break
        }
    }

    function reset() {
        status.value = 'idle'
        statusMessage.value = ''
        progress.value = 0
        result.value = ''
        error.value = ''
    }

    return {
        status, statusMessage, progress, result, error, isRunning,
        startTask, stopTask, handleWsMessage, reset,
    }
})
