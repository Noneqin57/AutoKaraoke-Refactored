/**
 * 音频播放 Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAudioStore = defineStore('audio', () => {
    const fileId = ref('')
    const filename = ref('')
    const fileSize = ref(0)
    const currentTime = ref(0)
    const duration = ref(0)
    const isPlaying = ref(false)

    const progress = computed(() =>
        duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0
    )

    function setFile(id: string, name: string, size: number) {
        fileId.value = id
        filename.value = name
        fileSize.value = size
    }

    function reset() {
        fileId.value = ''
        filename.value = ''
        fileSize.value = 0
        currentTime.value = 0
        duration.value = 0
        isPlaying.value = false
    }

    return {
        fileId, filename, fileSize, currentTime, duration, isPlaying, progress,
        setFile, reset,
    }
})
