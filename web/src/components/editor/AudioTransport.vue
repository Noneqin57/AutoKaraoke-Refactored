<template>
  <div class="audio-transport">
    <!-- 进度条 -->
    <div class="audio-transport__progress" @click="handleProgressClick" ref="progressBar">
      <div class="audio-transport__progress-fill" :style="{ width: progress + '%' }"></div>
      <div class="audio-transport__progress-head" :style="{ left: progress + '%' }"></div>
    </div>

    <!-- 控制区 -->
    <div class="audio-transport__controls">
      <!-- 左: 时间 -->
      <div class="audio-transport__time">
        {{ formatTimestamp(currentTime) }} / {{ formatTimestamp(duration) }}
      </div>

      <!-- 中: 播放控制 -->
      <div class="audio-transport__btns">
        <button class="audio-transport__btn" @click="$emit('seek-backward', 5)" title="后退 5s">
          ⏪
        </button>
        <button
          class="audio-transport__btn audio-transport__btn--play"
          @click="$emit('toggle-play')"
          :title="isPlaying ? '暂停' : '播放'"
        >
          {{ isPlaying ? '⏸' : '▶️' }}
        </button>
        <button class="audio-transport__btn" @click="$emit('seek-forward', 5)" title="前进 5s">
          ⏩
        </button>
      </div>

      <!-- 右: 倍速 -->
      <div class="audio-transport__speed">
        <button
          v-for="rate in [0.5, 0.75, 1, 1.25, 1.5]"
          :key="rate"
          class="audio-transport__speed-btn"
          :class="{ active: playbackRate === rate }"
          @click="$emit('set-rate', rate)"
        >
          {{ rate }}x
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  currentTime: number
  duration: number
  progress: number
  isPlaying: boolean
  playbackRate: number
}>()

const emit = defineEmits<{
  'toggle-play': []
  'seek': [time: number]
  'seek-forward': [seconds: number]
  'seek-backward': [seconds: number]
  'set-rate': [rate: number]
}>()

const progressBar = ref<HTMLElement>()

function handleProgressClick(e: MouseEvent) {
  if (!progressBar.value || props.duration <= 0) return
  const rect = progressBar.value.getBoundingClientRect()
  const ratio = (e.clientX - rect.left) / rect.width
  emit('seek', ratio * props.duration)
}

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.audio-transport {
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.audio-transport__progress {
  position: relative;
  height: 6px;
  background: var(--color-progress-bg);
  cursor: pointer;
}
.audio-transport__progress:hover {
  height: 8px;
}
.audio-transport__progress-fill {
  height: 100%;
  background: var(--color-accent);
  transition: width 0.05s linear;
}
.audio-transport__progress-head {
  position: absolute;
  top: 50%;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-accent);
  transform: translate(-50%, -50%);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.audio-transport__progress:hover .audio-transport__progress-head {
  opacity: 1;
}
.audio-transport__controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm) var(--space-md);
}
.audio-transport__time {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  min-width: 90px;
}
.audio-transport__btns {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.audio-transport__btn {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--color-btn-secondary);
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}
.audio-transport__btn:hover {
  background: var(--color-btn-secondary-hover);
}
.audio-transport__btn--play {
  width: 44px;
  height: 44px;
  background: var(--color-accent);
  color: white;
  font-size: 20px;
}
.audio-transport__btn--play:hover {
  background: var(--color-accent-hover);
  transform: scale(1.05);
}
.audio-transport__speed {
  display: flex;
  gap: 2px;
}
.audio-transport__speed-btn {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  background: transparent;
  transition: all var(--transition-fast);
}
.audio-transport__speed-btn:hover {
  color: var(--color-text);
  background: var(--color-bg-tertiary);
}
.audio-transport__speed-btn.active {
  color: var(--color-accent);
  font-weight: var(--font-weight-semibold);
  background: var(--color-accent-soft);
}
</style>
