<template>
  <div class="editor-view" tabindex="0" @keydown="handleKeydown" ref="viewEl">
    <!-- 无内容时的空状态 -->
    <div v-if="!editorStore.lrcContent" class="editor-view__empty">
      <div class="editor-view__empty-icon">🎵</div>
      <h2>没有歌词内容</h2>
      <p>请先在<router-link to="/">生成页面</router-link>生成歌词，或直接粘贴 LRC 内容。</p>
      <textarea
        class="editor-view__paste-area"
        placeholder="在这里粘贴 LRC 内容..."
        @paste="handlePaste"
      ></textarea>
    </div>

    <!-- 编辑器主体 -->
    <template v-else>
      <!-- 快捷键提示 -->
      <div class="editor-view__tips">
        💡 <b>空格</b>=播放/暂停 | <b>Enter</b>=打轴并跳下一行 | <b>↑↓</b>=选择行 | <b>Ctrl+←→</b>=微调±100ms | <b>双击</b>=跳转播放
      </div>

      <!-- 顶部: 预览 + 音频 -->
      <div class="editor-view__top">
        <KaraokePreview
          :lines="editorStore.lines"
          :current-time="player.currentTime.value"
        />
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
      </div>

      <!-- 底部: 歌词表格 -->
      <LrcTable
        :lines="editorStore.lines"
        :active-index="activeLineIndex"
        :selected-index="editorStore.selectedLineIndex"
        @select="(i) => editorStore.selectedLineIndex = i"
        @seek-to="(t) => player.seek(t)"
        @set-time="setCurrentTime"
        @update-line="handleUpdateLine"
      />

      <!-- 底部操作栏 -->
      <div class="editor-view__toolbar">
        <div class="editor-view__toolbar-left">
          <span class="editor-view__line-count">
            {{ editorStore.lines.length }} 行
          </span>
          <span v-if="editorStore.isDirty" class="editor-view__dirty">● 未保存</span>
        </div>
        <div class="editor-view__toolbar-right">
          <select v-model="exportEncoding" class="editor-view__encoding">
            <option value="utf-8">UTF-8</option>
            <option value="utf-8-sig">UTF-8 BOM</option>
            <option value="gbk">GBK</option>
          </select>
          <button class="editor-view__btn" @click="exportLrc">
            💾 导出 LRC
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import KaraokePreview from '@/components/editor/KaraokePreview.vue'
import AudioTransport from '@/components/editor/AudioTransport.vue'
import LrcTable from '@/components/editor/LrcTable.vue'
import { useEditorStore, type LrcLine } from '@/stores/editorStore'
import { useAudioStore } from '@/stores/audioStore'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { fileApi } from '@/api/client'
import { formatMs as formatTime } from '@/utils/time'

const editorStore = useEditorStore()
const audioStore = useAudioStore()
const player = useAudioPlayer()
const playbackRate = ref(1)
const exportEncoding = ref('utf-8')
const viewEl = ref<HTMLElement>()

// 当前活跃行（跟随播放位置）
const activeLineIndex = computed(() => {
  const t = player.currentTime.value
  const lines = editorStore.lines
  for (let i = lines.length - 1; i >= 0; i--) {
    if (t >= lines[i]!.startTime) return i
  }
  return -1
})

// 加载音频
onMounted(() => {
  if (audioStore.fileId) {
    player.load(audioStore.fileId)
  }
  // 自动聚焦
  viewEl.value?.focus()
})

// 监听音频文件变化
watch(() => audioStore.fileId, (newId) => {
  if (newId) player.load(newId)
})

// === 操作 ===

function setRate(rate: number) {
  playbackRate.value = rate
  player.setPlaybackRate(rate)
}

function setCurrentTime(lineIndex: number) {
  if (lineIndex >= 0 && lineIndex < editorStore.lines.length) {
    editorStore.updateLine(lineIndex, { startTime: player.currentTime.value })
  }
}

function handleUpdateLine(index: number, updates: Partial<LrcLine>) {
  editorStore.updateLine(index, updates)
}

function handlePaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text')
  if (text) {
    editorStore.setContent(text)
  }
}

async function exportLrc() {
  const content = buildLrcContent()
  await fileApi.downloadLrc(content, exportEncoding.value, 'edited.lrc')
}

function buildLrcContent(): string {
  return editorStore.lines.map(line => {
    const tag = `[${formatTime(line.startTime)}]`

    // 逐字标签或普通文本
    let lineStr: string
    if (line.words.length > 0) {
      const wordTags = line.words.map(w => `[${formatTime(w.startTime)}]${w.text}`).join('')
      lineStr = `${tag}${wordTags}`
    } else {
      lineStr = `${tag}${line.text}`
    }

    // 追加翻译行
    if (line.translation) {
      lineStr += `\n${tag}${line.translation}`
    }
    return lineStr
  }).join('\n')
}

/** 键盘快捷键 - 逐行模式 */
function handleKeydown(e: KeyboardEvent) {
  // 忽略输入框中的快捷键
  if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'TEXTAREA') return

  switch (e.key) {
    case ' ':
      e.preventDefault()
      player.togglePlay()
      break
    case 'Enter':
      e.preventDefault()
      stampCurrentLine()
      break
    case 'ArrowUp':
      e.preventDefault()
      if (editorStore.selectedLineIndex > 0) {
        editorStore.selectedLineIndex--
      }
      break
    case 'ArrowDown':
      e.preventDefault()
      if (editorStore.selectedLineIndex < editorStore.lines.length - 1) {
        editorStore.selectedLineIndex++
      }
      break
    case 'ArrowLeft':
      if (e.ctrlKey) {
        e.preventDefault()
        adjustTimestamp(-0.1)
      }
      break
    case 'ArrowRight':
      if (e.ctrlKey) {
        e.preventDefault()
        adjustTimestamp(0.1)
      }
      break
  }
}

/** Enter 打轴：将当前播放时间设为选中行的开始时间，并自动跳下一行 */
function stampCurrentLine() {
  const idx = editorStore.selectedLineIndex
  if (idx < 0) return

  const currentTime = player.currentTime.value
  editorStore.updateLine(idx, { startTime: currentTime })

  // 自动跳到下一行
  if (idx < editorStore.lines.length - 1) {
    editorStore.selectedLineIndex = idx + 1
  }
}

/** 微调选中行的时间戳 */
function adjustTimestamp(deltaSec: number) {
  const idx = editorStore.selectedLineIndex
  if (idx < 0) return

  const line = editorStore.lines[idx]
  if (!line) return

  const newTime = Math.max(0, line.startTime + deltaSec)
  editorStore.updateLine(idx, { startTime: newTime })
}
</script>

<style scoped>
.editor-view {
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

.editor-view__tips {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  background: var(--color-accent-soft);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
}

.editor-view__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: var(--space-md);
}
.editor-view__empty-icon {
  font-size: 64px;
  opacity: 0.3;
}
.editor-view__empty h2 {
  font-size: var(--font-size-xl);
  color: var(--color-text-secondary);
}
.editor-view__empty p {
  color: var(--color-text-tertiary);
}
.editor-view__empty a {
  color: var(--color-accent);
}
.editor-view__paste-area {
  width: 100%;
  max-width: 500px;
  min-height: 120px;
  padding: var(--space-md);
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  resize: vertical;
  outline: none;
}
.editor-view__paste-area:focus {
  border-color: var(--color-accent);
}

.editor-view__top {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.editor-view__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm) var(--space-md);
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
}
.editor-view__toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}
.editor-view__line-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.editor-view__dirty {
  font-size: var(--font-size-xs);
  color: var(--color-warning);
  font-weight: var(--font-weight-medium);
}
.editor-view__toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.editor-view__encoding {
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-input-bg);
  color: var(--color-text);
  font-size: var(--font-size-xs);
}
.editor-view__btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  background: var(--color-accent);
  color: white;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  transition: all var(--transition-fast);
}
.editor-view__btn:hover {
  background: var(--color-accent-hover);
}
</style>
