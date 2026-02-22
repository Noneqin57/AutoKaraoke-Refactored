<template>
  <div class="main-view">
    <!-- 标题区 -->
    <div class="main-view__hero">
      <h1>🎤 逐字歌词生成</h1>
      <p>基于 Whisper 的智能歌词对齐引擎</p>
    </div>

    <!-- 主内容 -->
    <div class="main-view__content">
      <!-- 音频选择 -->
      <AudioSelector
        @uploaded="onAudioUploaded"
        @removed="onAudioRemoved"
        @error="showError"
      />

      <!-- 歌词区域（左右分栏） -->
      <div class="main-view__lyrics-row">
        <LyricsInput
          v-model="lyricsText"
          @lyrics-parsed="onLyricsParsed"
          @error="showError"
        />
        <LyricsOutput
          :model-value="taskStore.result"
          @edit="goToEditor"
        />
      </div>

      <!-- 控制栏 -->
      <GenerateControls
        :is-running="taskStore.isRunning"
        :has-audio="!!audioStore.fileId"
        :msst-models="msstModels"
        v-model:forceCalibration="forceCalibration"
        v-model:avgDistribution="avgDistribution"
        v-model:enableMsst="enableMsst"
        v-model:msstModelKey="msstModelKey"
        @start="startGeneration"
        @stop="stopGeneration"
      />

      <!-- 状态栏 -->
      <StatusBar
        :status="taskStore.status"
        :message="taskStore.statusMessage"
        :progress="taskStore.progress"
        :has-result="!!taskStore.result"
        v-model:encoding="encoding"
        @save="saveResult"
      />

      <!-- 错误提示 -->
      <Transition name="fade">
        <div v-if="errorMessage" class="main-view__error" @click="errorMessage = ''">
          ⚠️ {{ errorMessage }}
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'MainView' })
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import AudioSelector from '@/components/main/AudioSelector.vue'
import LyricsInput from '@/components/main/LyricsInput.vue'
import LyricsOutput from '@/components/main/LyricsOutput.vue'
import GenerateControls from '@/components/main/GenerateControls.vue'
import StatusBar from '@/components/main/StatusBar.vue'
import { useAudioStore } from '@/stores/audioStore'
import { useTaskStore } from '@/stores/taskStore'
import { useEditorStore } from '@/stores/editorStore'
import { useWebSocket } from '@/composables/useWebSocket'
import { fileApi, msstApi, type MsstModelItem } from '@/api/client'

const router = useRouter()
const audioStore = useAudioStore()
const taskStore = useTaskStore()
const editorStore = useEditorStore()

// 本地状态
const lyricsText = ref('')
const rawLrcContent = ref('')
const forceCalibration = ref(true)
const avgDistribution = ref(false)
const enableMsst = ref(false)
const msstModelKey = ref('')
const msstModels = ref<MsstModelItem[]>([])
const encoding = ref('utf-8')
const errorMessage = ref('')

// WebSocket 连接
const { connect, disconnect } = useWebSocket('/api/task/ws', {
  onMessage: (data) => taskStore.handleWsMessage(data),
  onConnected: () => console.log('[WS] Task WebSocket connected'),
})

onMounted(() => {
  connect()
  loadMsstModels()
})

onUnmounted(() => {
  disconnect()
})

// === 事件处理 ===

function onAudioUploaded(fileId: string) {
  errorMessage.value = ''
}

function onAudioRemoved() {
  // 重置
}

function onLyricsParsed(data: { rawContent: string; timestamps: number[] }) {
  rawLrcContent.value = data.rawContent
}

async function loadMsstModels() {
  try {
    const data = await msstApi.list()
    msstModels.value = data.models
    // 设置默认选中已下载的第一个模型
    if (!msstModelKey.value) {
      const downloaded = data.models.find(m => m.is_downloaded)
      if (downloaded) {
        msstModelKey.value = downloaded.key
      } else if (data.models.length > 0) {
        msstModelKey.value = data.models[0]!.key
      }
    }
  } catch {
    // 后端未连接时静默
  }
}

async function startGeneration() {
  if (!audioStore.fileId) {
    showError('请先选择音频文件')
    return
  }

  errorMessage.value = ''

  await taskStore.startTask({
    audio_file_id: audioStore.fileId,
    lyrics_text: lyricsText.value,
    raw_lrc_content: rawLrcContent.value,
    enable_force_calibration: forceCalibration.value,
    enable_avg_distribution: avgDistribution.value,
    enable_msst: enableMsst.value,
    msst_model_key: msstModelKey.value,
  })
}

async function stopGeneration() {
  await taskStore.stopTask()
}

function goToEditor() {
  if (taskStore.result) {
    editorStore.setContent(taskStore.result)
    router.push('/editor')
  }
}

async function saveResult() {
  if (!taskStore.result) return
  try {
    await fileApi.downloadLrc(taskStore.result, encoding.value, 'output.lrc')
  } catch (e: any) {
    showError(e.message || '保存失败')
  }
}

function showError(msg: string) {
  errorMessage.value = msg
  setTimeout(() => {
    if (errorMessage.value === msg) errorMessage.value = ''
  }, 5000)
}
</script>

<style scoped>
.main-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-lg) var(--space-lg) var(--space-2xl);
}

.main-view__hero {
  text-align: center;
  margin-bottom: var(--space-xl);
}
.main-view__hero h1 {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  margin-bottom: var(--space-xs);
  background: linear-gradient(135deg, var(--color-accent), var(--color-info));
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.main-view__hero p {
  color: var(--color-text-secondary);
  font-size: var(--font-size-md);
}

.main-view__content {
  width: 100%;
  max-width: 1000px;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.main-view__lyrics-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

.main-view__error {
  padding: var(--space-sm) var(--space-md);
  background: rgba(231, 76, 60, 0.1);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 响应式 */
@media (max-width: 768px) {
  .main-view__lyrics-row {
    grid-template-columns: 1fr;
  }
}
</style>
