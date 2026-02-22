<template>
  <div class="word-editor-view" tabindex="0" @keydown="handleKeydown" ref="viewEl">
    <!-- 无内容时 -->
    <div v-if="!editorStore.lrcContent" class="word-editor-view__empty">
      <div class="word-editor-view__empty-icon">🎵</div>
      <h2>没有歌词内容</h2>
      <p>请先在<router-link to="/">生成页面</router-link>生成歌词，或前往<router-link to="/editor">逐行编辑器</router-link>粘贴 LRC 内容。</p>
    </div>

    <template v-else>
      <!-- 模式选择：行选择 vs 逐字编辑 -->
      <div v-if="!editingLine" class="word-editor-view__line-select">
        <!-- 快捷键提示 -->
        <div class="word-editor-view__tips">
          💡 点击选择一行进入逐字编辑模式
        </div>

        <!-- 音频播放器 -->
        <AudioTransport
          v-if="audioStore.fileId"
          :current-time="player.currentTime.value"
          :duration="player.duration.value"
          :progress="player.progress.value"
          :is-playing="player.isPlaying.value"
          :playback-rate="playbackRate"
          @toggle-play="player.togglePlay()"
          @seek="(t) => player.seek(t)"
          @seek-forward="(s) => player.seek(player.currentTime.value + s)"
          @seek-backward="(s) => player.seek(player.currentTime.value - s)"
          @set-rate="setRate"
        />

        <!-- 行列表 -->
        <div class="word-editor-view__line-list">
          <div
            v-for="(line, i) in editorStore.lines"
            :key="i"
            class="word-editor-view__line-item"
            :class="{ 'word-editor-view__line-item--has-words': line.words.length > 0 }"
            @click="enterWordMode(i)"
          >
            <span class="word-editor-view__line-idx">{{ i + 1 }}</span>
            <span class="word-editor-view__line-time">{{ formatTime(line.startTime) }}</span>
            <span class="word-editor-view__line-text">{{ line.text }}</span>
            <span v-if="line.words.length > 0" class="word-editor-view__line-badge">✓ 已打轴</span>
          </div>
        </div>
      </div>

      <!-- 逐字编辑模式 -->
      <div v-else class="word-editor-view__word-mode">
        <!-- 快捷键提示 -->
        <div class="word-editor-view__tips">
          💡 <b>Enter</b>=打点并跳下一字 | <b>空格</b>=播放/暂停 | <b>←→</b>=选择字 | <b>↑↓</b>=微调±50ms | <b>Esc</b>=返回
        </div>

        <!-- 卡拉OK 预览 -->
        <div class="word-editor-view__preview">
          <span
            v-for="(token, i) in tokens"
            :key="i"
            class="word-editor-view__preview-char"
            :class="{
              'word-editor-view__preview-char--sung': getCharStatus(i) === 'sung',
              'word-editor-view__preview-char--active': getCharStatus(i) === 'active',
            }"
          >{{ token.char }}</span>
        </div>

        <!-- 区间信息 -->
        <div class="word-editor-view__range">
          当前行: {{ formatTime(editingLine.startTime) }} → {{ formatTime(editingLine.endTime) }}
          <span class="word-editor-view__current-time">⏱ {{ formatTime(player.currentTime.value) }}</span>
        </div>

        <!-- 音频播放器 -->
        <AudioTransport
          v-if="audioStore.fileId"
          :current-time="player.currentTime.value"
          :duration="player.duration.value"
          :progress="player.progress.value"
          :is-playing="player.isPlaying.value"
          :playback-rate="playbackRate"
          @toggle-play="player.togglePlay()"
          @seek="(t) => player.seek(t)"
          @seek-forward="(s) => player.seek(player.currentTime.value + s)"
          @seek-backward="(s) => player.seek(player.currentTime.value - s)"
          @set-rate="setRate"
        />

        <!-- 字时间表格 -->
        <div class="word-editor-view__char-table-wrapper">
          <div class="word-editor-view__char-table">
            <!-- 字行 -->
            <div class="word-editor-view__char-row word-editor-view__char-row--chars">
              <div
                v-for="(token, i) in tokens"
                :key="i"
                class="word-editor-view__char-cell"
                :class="{
                  'word-editor-view__char-cell--selected': i === selectedCharIndex,
                  'word-editor-view__char-cell--edited': token.edited,
                }"
                @click="selectChar(i)"
              >{{ token.char }}</div>
            </div>
            <!-- 时间行 -->
            <div class="word-editor-view__char-row word-editor-view__char-row--times">
              <div
                v-for="(token, i) in tokens"
                :key="i"
                class="word-editor-view__time-cell"
                :class="{ 'word-editor-view__time-cell--selected': i === selectedCharIndex }"
              >{{ formatTime(token.time) }}</div>
            </div>
          </div>
        </div>

        <!-- 操作栏 -->
        <div class="word-editor-view__actions">
          <button class="word-editor-view__btn word-editor-view__btn--secondary" @click="replayLine">
            ⏪ 重播本句
          </button>
          <button class="word-editor-view__btn word-editor-view__btn--primary" @click="saveAndExit">
            💾 保存并返回
          </button>
          <button class="word-editor-view__btn" @click="exitWordMode">
            取消
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import AudioTransport from '@/components/editor/AudioTransport.vue'
import { useEditorStore, type LrcLine, type LrcWord } from '@/stores/editorStore'
import { useAudioStore } from '@/stores/audioStore'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { formatMs as formatTime } from '@/utils/time'

interface CharToken {
  char: string
  time: number
  edited: boolean
}

const editorStore = useEditorStore()
const audioStore = useAudioStore()
const player = useAudioPlayer()
const viewEl = ref<HTMLElement>()
const playbackRate = ref(1)

// 逐字编辑状态
const editingLineIndex = ref(-1)
const editingLine = computed(() =>
  editingLineIndex.value >= 0 ? editorStore.lines[editingLineIndex.value] : null
)
const tokens = ref<CharToken[]>([])
const selectedCharIndex = ref(0)

// 自动暂停监视
let stopWatchHandle: ReturnType<typeof watch> | null = null

// 加载音频
onMounted(() => {
  if (audioStore.fileId) {
    player.load(audioStore.fileId)
  }
  viewEl.value?.focus()
})

onUnmounted(() => {
  stopWatchHandle?.()
})

watch(() => audioStore.fileId, (newId) => {
  if (newId) player.load(newId)
})

function setRate(rate: number) {
  playbackRate.value = rate
  player.setPlaybackRate(rate)
}

// === 行选择 ===

function enterWordMode(lineIndex: number) {
  const line = editorStore.lines[lineIndex]
  if (!line) return

  editingLineIndex.value = lineIndex
  selectedCharIndex.value = 0

  // 将行拆分为单字 token
  if (line.words.length > 0) {
    // 已有逐字数据，用现有数据
    tokens.value = line.words.map(w => ({
      char: w.text,
      time: w.startTime,
      edited: false,
    }))
  } else {
    // 无逐字数据，将文本拆分为单字
    const chars = [...line.text]
    const duration = line.endTime - line.startTime
    const charDuration = chars.length > 0 ? duration / chars.length : 0
    tokens.value = chars.map((ch, i) => ({
      char: ch,
      time: line.startTime + i * charDuration,
      edited: false,
    }))
  }

  // 定位到句首前 1 秒
  const seekPos = Math.max(0, line.startTime - 1)
  player.seek(seekPos)

  // 监视播放位置，到行尾自动暂停
  stopWatchHandle?.()
  stopWatchHandle = watch(() => player.currentTime.value, (t) => {
    if (editingLine.value && t >= editingLine.value.endTime + 0.2) {
      if (player.isPlaying.value) {
        player.togglePlay()
      }
    }
  })

  // 聚焦
  setTimeout(() => viewEl.value?.focus(), 50)
}

function exitWordMode() {
  editingLineIndex.value = -1
  tokens.value = []
  stopWatchHandle?.()
  viewEl.value?.focus()
}

function replayLine() {
  if (!editingLine.value) return
  player.seek(Math.max(0, editingLine.value.startTime - 1))
  if (!player.isPlaying.value) {
    player.togglePlay()
  }
}

// === 逐字打轴逻辑 ===

function stampCurrentChar() {
  if (selectedCharIndex.value < 0 || selectedCharIndex.value >= tokens.value.length) return

  const t = player.currentTime.value
  tokens.value[selectedCharIndex.value]!.time = t
  tokens.value[selectedCharIndex.value]!.edited = true

  // 自动跳到下一个字
  if (selectedCharIndex.value < tokens.value.length - 1) {
    selectedCharIndex.value++
  }
}

function adjustCharTime(deltaMs: number) {
  if (selectedCharIndex.value < 0 || selectedCharIndex.value >= tokens.value.length) return
  const token = tokens.value[selectedCharIndex.value]!
  token.time = Math.max(0, token.time + deltaMs / 1000)
  token.edited = true
}

function selectChar(i: number) {
  selectedCharIndex.value = i
  // 点击字时跳转到该字的时间
  const token = tokens.value[i]
  if (token) {
    player.seek(token.time)
    if (!player.isPlaying.value) {
      player.togglePlay()
    }
  }
}

/** 获取字的卡拉OK状态 */
function getCharStatus(i: number): 'sung' | 'active' | 'unsung' {
  const t = player.currentTime.value
  const token = tokens.value[i]!
  const nextToken = i < tokens.value.length - 1 ? tokens.value[i + 1] : null
  const nextTime = nextToken ? nextToken.time : (editingLine.value?.endTime ?? token.time + 1)

  if (t >= nextTime) return 'sung'
  if (t >= token.time) return 'active'
  return 'unsung'
}

/** 保存逐字结果 */
function saveAndExit() {
  if (editingLineIndex.value < 0 || tokens.value.length === 0) return

  const words: LrcWord[] = tokens.value.map((token, i) => {
    const nextToken = i < tokens.value.length - 1 ? tokens.value[i + 1] : null
    return {
      text: token.char,
      startTime: token.time,
      endTime: nextToken ? nextToken.time : (editingLine.value?.endTime ?? token.time),
    }
  })

  editorStore.updateLine(editingLineIndex.value, {
    words,
    startTime: tokens.value[0]!.time,
  })

  exitWordMode()
}

// === 键盘快捷键 ===

function handleKeydown(e: KeyboardEvent) {
  if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'TEXTAREA') return

  // 逐字模式快捷键
  if (editingLine.value) {
    switch (e.key) {
      case ' ':
        e.preventDefault()
        player.togglePlay()
        break
      case 'Enter':
        e.preventDefault()
        stampCurrentChar()
        break
      case 'ArrowLeft':
        e.preventDefault()
        if (selectedCharIndex.value > 0) selectedCharIndex.value--
        break
      case 'ArrowRight':
        e.preventDefault()
        if (selectedCharIndex.value < tokens.value.length - 1) selectedCharIndex.value++
        break
      case 'ArrowUp':
        e.preventDefault()
        adjustCharTime(50)
        break
      case 'ArrowDown':
        e.preventDefault()
        adjustCharTime(-50)
        break
      case 'Escape':
        e.preventDefault()
        exitWordMode()
        break
    }
    return
  }

  // 行选择模式快捷键
  switch (e.key) {
    case ' ':
      e.preventDefault()
      player.togglePlay()
      break
  }
}
</script>

<style scoped>
.word-editor-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  outline: none;
}

.word-editor-view__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: var(--space-md);
}
.word-editor-view__empty-icon {
  font-size: 64px;
  opacity: 0.3;
}
.word-editor-view__empty h2 {
  color: var(--color-text-secondary);
}
.word-editor-view__empty a {
  color: var(--color-accent);
}

.word-editor-view__tips {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background: var(--color-accent-soft);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
}

/* === 行选择 === */
.word-editor-view__line-select {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}
.word-editor-view__line-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.word-editor-view__line-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.word-editor-view__line-item:hover {
  border-color: var(--color-accent);
  background: var(--color-accent-soft);
}
.word-editor-view__line-item--has-words {
  border-left: 3px solid var(--color-success);
}
.word-editor-view__line-idx {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  min-width: 24px;
  text-align: center;
}
.word-editor-view__line-time {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--color-accent);
  min-width: 70px;
}
.word-editor-view__line-text {
  flex: 1;
  font-size: var(--font-size-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.word-editor-view__line-badge {
  font-size: var(--font-size-xs);
  color: var(--color-success);
  padding: 2px 6px;
  background: rgba(52, 199, 89, 0.1);
  border-radius: var(--radius-sm);
}

/* === 逐字编辑模式 === */
.word-editor-view__word-mode {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* 预览区 */
.word-editor-view__preview {
  background: var(--color-karaoke-bg);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  text-align: center;
  font-size: 28px;
  font-weight: var(--font-weight-bold);
  min-height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 0;
}
.word-editor-view__preview-char {
  color: var(--color-karaoke-unsung);
  transition: color 0.1s ease;
}
.word-editor-view__preview-char--sung {
  color: var(--color-karaoke-sung);
}
.word-editor-view__preview-char--active {
  color: var(--color-karaoke-active);
}

/* 区间信息 */
.word-editor-view__range {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  text-align: center;
  font-family: var(--font-mono);
}
.word-editor-view__current-time {
  color: var(--color-accent);
  font-weight: var(--font-weight-bold);
  margin-left: var(--space-md);
}

/* 字时间表格 */
.word-editor-view__char-table-wrapper {
  overflow-x: auto;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  background: var(--color-card-bg);
  padding: var(--space-md);
}
.word-editor-view__char-table {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.word-editor-view__char-row {
  display: flex;
  gap: 2px;
}
.word-editor-view__char-cell {
  min-width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: var(--font-weight-bold);
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  user-select: none;
}
.word-editor-view__char-cell:hover {
  background: var(--color-bg-tertiary);
}
.word-editor-view__char-cell--selected {
  background: var(--color-accent) !important;
  color: white;
}
.word-editor-view__char-cell--edited {
  background: rgba(255, 214, 10, 0.2);
}
.word-editor-view__time-cell {
  min-width: 48px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
  color: var(--color-text-tertiary);
  border-radius: var(--radius-sm);
}
.word-editor-view__time-cell--selected {
  color: var(--color-accent);
  font-weight: var(--font-weight-bold);
}

/* 操作栏 */
.word-editor-view__actions {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  justify-content: flex-end;
}
.word-editor-view__btn {
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  transition: all var(--transition-fast);
  background: var(--color-btn-secondary);
  color: var(--color-text);
}
.word-editor-view__btn:hover {
  background: var(--color-bg-tertiary);
}
.word-editor-view__btn--primary {
  background: var(--color-success);
  color: white;
}
.word-editor-view__btn--primary:hover {
  filter: brightness(1.1);
}
.word-editor-view__btn--secondary {
  background: var(--color-accent);
  color: white;
}
.word-editor-view__btn--secondary:hover {
  background: var(--color-accent-hover);
}
</style>
