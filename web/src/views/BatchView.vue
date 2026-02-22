<template>
  <div class="batch-view">
    <!-- 标题区 -->
    <div class="batch-view__hero">
      <h1>📦 批量歌词生成</h1>
      <p>同时处理多首歌曲，逐个自动生成逐字歌词</p>
    </div>

    <!-- 警告横幅 -->
    <div class="batch-view__warning">
      <span class="batch-view__warning-icon">⚠️</span>
      <span>批量生成歌词无法再次修改原歌词文本和生成歌词时间轴，请确保原歌词是正常排版</span>
    </div>

    <div class="batch-view__content">
      <!-- 文件导入区 -->
      <div class="batch-view__import" v-if="!batchStore.isRunning">
        <div
          class="batch-view__dropzone"
          :class="{ 'batch-view__dropzone--dragover': isDragging }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
          @click="openFilePicker"
        >
          <div class="batch-view__dropzone-icon">📁</div>
          <div class="batch-view__dropzone-text">
            拖拽文件到此处，或点击选择文件
          </div>
          <div class="batch-view__dropzone-hint">
            支持音频（.mp3 .wav .flac .m4a）和歌词（.lrc .txt）文件<br>
            系统将按<strong>文件名</strong>自动匹配音频与歌词
          </div>
        </div>
        <input
          ref="fileInput"
          type="file"
          multiple
          accept=".mp3,.wav,.flac,.m4a,.ogg,.wma,.aac,.lrc,.txt,.srt"
          style="display: none"
          @change="handleFileSelect"
        />
      </div>

      <!-- 配对列表 -->
      <div class="batch-view__list" v-if="batchStore.hasItems">
        <div class="batch-view__list-header">
          <h3>任务列表 ({{ batchStore.items.length }} 项)</h3>
          <div class="batch-view__list-actions" v-if="!batchStore.isRunning">
            <button class="btn btn--ghost btn--sm" @click="batchStore.clearAll()">
              🗑️ 清空
            </button>
          </div>
        </div>

        <div class="batch-view__table-wrap">
          <table class="batch-view__table">
            <thead>
              <tr>
                <th class="col-idx">#</th>
                <th class="col-name">名称</th>
                <th class="col-audio">音频</th>
                <th class="col-lyrics">歌词</th>
                <th class="col-status">状态</th>
                <th class="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, i) in batchStore.items"
                :key="item.id"
                class="batch-view__row"
                :class="`batch-view__row--${item.status}`"
              >
                <td class="col-idx">{{ i + 1 }}</td>
                <td class="col-name">{{ item.name }}</td>
                <td class="col-audio">
                  <span class="file-badge file-badge--audio">
                    🎵 {{ item.audioFile?.name || '—' }}
                  </span>
                </td>
                <td class="col-lyrics">
                  <span class="file-badge file-badge--lyrics">
                    📄 {{ item.lyricsFile?.name || '—' }}
                  </span>
                </td>
                <td class="col-status">
                  <div class="status-cell">
                    <span
                      class="status-dot"
                      :class="`status-dot--${item.status}`"
                    ></span>
                    <span class="status-text">{{ getStatusLabel(item) }}</span>
                    <!-- Progress bar for running items -->
                    <div v-if="item.status === 'running'" class="mini-progress">
                      <div
                        class="mini-progress__bar"
                        :style="{ width: item.progress + '%' }"
                      ></div>
                    </div>
                  </div>
                </td>
                <td class="col-actions">
                  <button
                    v-if="item.status === 'success'"
                    class="btn btn--ghost btn--xs"
                    @click="downloadSingle(i)"
                    title="下载结果"
                  >
                    💾
                  </button>
                  <button
                    v-if="!batchStore.isRunning"
                    class="btn btn--ghost btn--xs"
                    @click="batchStore.removeItem(item.id)"
                    title="移除"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 控制区 -->
      <div class="batch-view__controls" v-if="batchStore.hasItems">
        <div class="batch-view__options" v-if="!batchStore.isRunning">
          <label class="batch-view__checkbox">
            <input type="checkbox" v-model="forceCalibration" />
            <span>强制纠偏</span>
          </label>
          <label class="batch-view__checkbox">
            <input type="checkbox" v-model="avgDistribution" />
            <span>平均分配</span>
          </label>
        </div>

        <div class="batch-view__buttons">
          <button
            v-if="!batchStore.isRunning"
            class="btn btn--primary"
            @click="startBatch"
            :disabled="batchStore.items.length === 0"
          >
            🚀 开始批量生成
          </button>
          <button
            v-if="batchStore.isRunning"
            class="btn btn--danger"
            @click="batchStore.stopBatch()"
          >
            ⏹️ 停止
          </button>
          <button
            v-if="batchStore.successCount > 0 && !batchStore.isRunning"
            class="btn btn--accent"
            @click="downloadAll"
          >
            📦 下载全部 ({{ batchStore.successCount }})
          </button>
        </div>

        <!-- 总进度 -->
        <div v-if="batchStore.isRunning" class="batch-view__overall-progress">
          <div class="batch-view__overall-bar">
            <div
              class="batch-view__overall-fill"
              :style="{ width: overallProgress + '%' }"
            ></div>
          </div>
          <span class="batch-view__overall-text">
            {{ batchStore.completedCount }} / {{ batchStore.totalItems }}
          </span>
        </div>
      </div>

      <!-- 错误提示 -->
      <Transition name="fade">
        <div v-if="errorMessage" class="batch-view__error" @click="errorMessage = ''">
          ⚠️ {{ errorMessage }}
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'BatchView' })
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useBatchStore, type BatchItem } from '@/stores/batchStore'
import { useWebSocket } from '@/composables/useWebSocket'
import { batchApi } from '@/api/client'

const batchStore = useBatchStore()
const fileInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const forceCalibration = ref(true)
const avgDistribution = ref(false)
const errorMessage = ref('')

const AUDIO_EXTS = ['.mp3', '.wav', '.flac', '.m4a', '.ogg', '.wma', '.aac']
const LYRICS_EXTS = ['.lrc', '.txt', '.srt']

// WebSocket
const { connect, disconnect } = useWebSocket('/api/batch/ws', {
  onMessage: (data) => batchStore.handleWsMessage(data),
  onConnected: () => console.log('[WS] Batch WebSocket connected'),
})

onMounted(() => connect())
onUnmounted(() => disconnect())

const overallProgress = computed(() => {
  if (batchStore.totalItems === 0) return 0
  return Math.round((batchStore.completedCount / batchStore.totalItems) * 100)
})

function getExt(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.substring(dot).toLowerCase() : ''
}

function getStem(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.substring(0, dot) : name
}

function openFilePicker() {
  fileInput.value?.click()
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) {
    processFiles(Array.from(input.files))
  }
  input.value = ''
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  if (e.dataTransfer?.files) {
    processFiles(Array.from(e.dataTransfer.files))
  }
}

function processFiles(files: File[]) {
  const audioFiles: File[] = []
  const lyricsFiles: File[] = []

  for (const file of files) {
    const ext = getExt(file.name)
    if (AUDIO_EXTS.includes(ext)) {
      audioFiles.push(file)
    } else if (LYRICS_EXTS.includes(ext)) {
      lyricsFiles.push(file)
    }
  }

  // Auto-pair by filename stem
  const lyricsMap = new Map<string, File>()
  for (const lf of lyricsFiles) {
    lyricsMap.set(getStem(lf.name).toLowerCase(), lf)
  }

  let matched = 0
  for (const af of audioFiles) {
    const stem = getStem(af.name).toLowerCase()
    const lf = lyricsMap.get(stem)
    if (lf) {
      batchStore.addPair(af, lf)
      lyricsMap.delete(stem)
      matched++
    }
  }

  // Report unmatched
  const unmatchedAudio = audioFiles.length - matched
  const unmatchedLyrics = lyricsMap.size
  if (unmatchedAudio > 0 || unmatchedLyrics > 0) {
    const msgs: string[] = []
    if (unmatchedAudio > 0) msgs.push(`${unmatchedAudio} 个音频无匹配歌词`)
    if (unmatchedLyrics > 0) msgs.push(`${unmatchedLyrics} 个歌词无匹配音频`)
    errorMessage.value = `已匹配 ${matched} 对，${msgs.join('，')}。请确保文件名一致。`
    setTimeout(() => { if (errorMessage.value) errorMessage.value = '' }, 8000)
  }
}

function getStatusLabel(item: BatchItem): string {
  switch (item.status) {
    case 'pending': return '等待中'
    case 'uploading': return '上传中'
    case 'running': return item.statusMessage || '处理中'
    case 'success': return '✅ 完成'
    case 'error': return `❌ ${item.error || '失败'}`
    case 'aborted': return '已中止'
    default: return ''
  }
}

async function startBatch() {
  errorMessage.value = ''
  await batchStore.startBatch({
    enableForceCalibration: forceCalibration.value,
    enableAvgDistribution: avgDistribution.value,
    enableMsst: false,
    msstModelKey: '',
  })
}

async function downloadAll() {
  try {
    await batchApi.downloadAll()
  } catch (e: any) {
    errorMessage.value = e.message
  }
}

async function downloadSingle(index: number) {
  try {
    const item = batchStore.items[index]
    await batchApi.downloadSingle(index, item?.name || 'result')
  } catch (e: any) {
    errorMessage.value = e.message
  }
}
</script>

<style scoped>
.batch-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-lg) var(--space-lg) var(--space-2xl);
}

.batch-view__hero {
  text-align: center;
  margin-bottom: var(--space-md);
}
.batch-view__hero h1 {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  margin-bottom: var(--space-xs);
  background: linear-gradient(135deg, #f39c12, #e74c3c);
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.batch-view__hero p {
  color: var(--color-text-secondary);
  font-size: var(--font-size-md);
}

/* Warning Banner */
.batch-view__warning {
  width: 100%;
  max-width: 1000px;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  margin-bottom: var(--space-lg);
  background: rgba(243, 156, 18, 0.1);
  border: 1px solid rgba(243, 156, 18, 0.4);
  border-radius: var(--radius-md);
  color: #f39c12;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}
.batch-view__warning-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.batch-view__content {
  width: 100%;
  max-width: 1000px;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* Dropzone */
.batch-view__dropzone {
  border: 2px dashed var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: var(--space-2xl) var(--space-xl);
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  background: var(--color-card-bg);
}
.batch-view__dropzone:hover,
.batch-view__dropzone--dragover {
  border-color: var(--color-accent);
  background: var(--color-accent-soft);
}
.batch-view__dropzone-icon {
  font-size: 48px;
  margin-bottom: var(--space-sm);
}
.batch-view__dropzone-text {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  margin-bottom: var(--space-xs);
}
.batch-view__dropzone-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

/* List */
.batch-view__list {
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.batch-view__list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-bg-secondary);
}
.batch-view__list-header h3 {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  margin: 0;
}

/* Table */
.batch-view__table-wrap {
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}
.batch-view__table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}
.batch-view__table th {
  padding: var(--space-xs) var(--space-sm);
  text-align: left;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--color-border-light);
  position: sticky;
  top: 0;
  background: var(--color-bg-secondary);
  z-index: 1;
}
.batch-view__table td {
  padding: var(--space-xs) var(--space-sm);
  border-bottom: 1px solid var(--color-border-light);
  vertical-align: middle;
}
.batch-view__row--success {
  background: rgba(46, 204, 113, 0.05);
}
.batch-view__row--error {
  background: rgba(231, 76, 60, 0.05);
}
.batch-view__row--running {
  background: var(--color-accent-soft);
}

.col-idx { width: 40px; text-align: center; color: var(--color-text-tertiary); font-family: var(--font-mono); }
.col-name { min-width: 120px; font-weight: var(--font-weight-medium); }
.col-audio, .col-lyrics { min-width: 150px; }
.col-status { min-width: 160px; }
.col-actions { width: 80px; text-align: center; }

.file-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-badge--audio { background: rgba(52, 152, 219, 0.1); color: #3498db; }
.file-badge--lyrics { background: rgba(155, 89, 182, 0.1); color: #9b59b6; }

/* Status */
.status-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.status-dot--pending { background: var(--color-text-tertiary); }
.status-dot--uploading { background: #f39c12; }
.status-dot--running { background: var(--color-accent); animation: pulse 1s infinite; }
.status-dot--success { background: #2ecc71; }
.status-dot--error { background: #e74c3c; }
.status-dot--aborted { background: #95a5a6; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.status-text {
  font-size: var(--font-size-xs);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-progress {
  width: 100%;
  height: 4px;
  background: var(--color-bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}
.mini-progress__bar {
  height: 100%;
  background: var(--color-accent);
  transition: width 0.3s ease;
  border-radius: 2px;
}

/* Controls */
.batch-view__controls {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md);
  background: var(--color-card-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
}
.batch-view__options {
  display: flex;
  gap: var(--space-lg);
}
.batch-view__checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}
.batch-view__checkbox input {
  accent-color: var(--color-accent);
}
.batch-view__buttons {
  display: flex;
  gap: var(--space-sm);
}

/* Overall Progress */
.batch-view__overall-progress {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}
.batch-view__overall-bar {
  flex: 1;
  height: 8px;
  background: var(--color-bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}
.batch-view__overall-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-accent), #2ecc71);
  transition: width 0.5s ease;
  border-radius: 4px;
}
.batch-view__overall-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
  white-space: nowrap;
}

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition: all var(--transition-fast);
  border: none;
}
.btn--primary {
  background: var(--color-accent);
  color: white;
}
.btn--primary:hover { filter: brightness(1.1); }
.btn--primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn--danger {
  background: #e74c3c;
  color: white;
}
.btn--danger:hover { filter: brightness(1.1); }
.btn--accent {
  background: #2ecc71;
  color: white;
}
.btn--accent:hover { filter: brightness(1.1); }
.btn--ghost {
  background: transparent;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-light);
}
.btn--ghost:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text);
}
.btn--sm { padding: var(--space-xs) var(--space-sm); font-size: var(--font-size-xs); }
.btn--xs { padding: 2px 6px; font-size: 12px; }

/* Error */
.batch-view__error {
  padding: var(--space-sm) var(--space-md);
  background: rgba(231, 76, 60, 0.1);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
