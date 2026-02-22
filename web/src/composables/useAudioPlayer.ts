/**
 * 音频播放器组合式函数
 *
 * 使用 HTML5 Audio 元素 + requestAnimationFrame 实现 ~16ms 精度更新。
 */
import { ref, onUnmounted, computed } from 'vue'
import { getAudioUrl } from '@/api/client'

export function useAudioPlayer() {
    let audio: HTMLAudioElement | null = null
    let rafId: number | null = null

    // 保存事件处理器引用，以便 destroy 时移除
    let onLoadedMetadata: (() => void) | null = null
    let onEnded: (() => void) | null = null
    let onError: (() => void) | null = null

    const isPlaying = ref(false)
    const currentTime = ref(0)   // 秒
    const duration = ref(0)       // 秒
    const isReady = ref(false)

    const progress = computed(() =>
        duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0
    )

    /** 加载音频文件 */
    function load(fileId: string) {
        destroy()
        audio = new Audio(getAudioUrl(fileId))
        audio.preload = 'auto'

        onLoadedMetadata = () => {
            duration.value = audio!.duration
            isReady.value = true
        }
        onEnded = () => {
            isPlaying.value = false
            stopRAF()
        }
        onError = () => {
            isReady.value = false
        }

        audio.addEventListener('loadedmetadata', onLoadedMetadata)
        audio.addEventListener('ended', onEnded)
        audio.addEventListener('error', onError)
    }

    /** requestAnimationFrame 循环更新当前时间 */
    function startRAF() {
        const tick = () => {
            if (audio) {
                currentTime.value = audio.currentTime
            }
            rafId = requestAnimationFrame(tick)
        }
        rafId = requestAnimationFrame(tick)
    }

    function stopRAF() {
        if (rafId !== null) {
            cancelAnimationFrame(rafId)
            rafId = null
        }
    }

    /** 播放 */
    function play() {
        if (!audio) return
        audio.play()
        isPlaying.value = true
        startRAF()
    }

    /** 暂停 */
    function pause() {
        if (!audio) return
        audio.pause()
        isPlaying.value = false
        stopRAF()
        if (audio) currentTime.value = audio.currentTime
    }

    /** 切换播放/暂停 */
    function togglePlay() {
        isPlaying.value ? pause() : play()
    }

    /** 跳转到指定时间（秒） */
    function seek(timeInSeconds: number) {
        if (!audio) return
        audio.currentTime = Math.max(0, Math.min(timeInSeconds, duration.value))
        currentTime.value = audio.currentTime
    }

    /** 设置播放速率 */
    function setPlaybackRate(rate: number) {
        if (audio) audio.playbackRate = rate
    }

    /** 设置音量 (0~1) */
    function setVolume(vol: number) {
        if (audio) audio.volume = Math.max(0, Math.min(1, vol))
    }

    /** 销毁 */
    function destroy() {
        stopRAF()
        if (audio) {
            // 移除所有事件监听器，防止泄漏
            if (onLoadedMetadata) audio.removeEventListener('loadedmetadata', onLoadedMetadata)
            if (onEnded) audio.removeEventListener('ended', onEnded)
            if (onError) audio.removeEventListener('error', onError)
            audio.pause()
            audio.src = ''
            audio = null
        }
        onLoadedMetadata = null
        onEnded = null
        onError = null
        isPlaying.value = false
        currentTime.value = 0
        duration.value = 0
        isReady.value = false
    }

    onUnmounted(destroy)

    return {
        isPlaying,
        currentTime,
        duration,
        progress,
        isReady,
        load,
        play,
        pause,
        togglePlay,
        seek,
        setPlaybackRate,
        setVolume,
        destroy,
    }
}
