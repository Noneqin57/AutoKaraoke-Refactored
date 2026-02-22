<template>
  <div class="path-settings">
    <h3 class="settings-section__title">📁 路径设置</h3>

    <!-- 模型目录 -->
    <div class="settings-field">
      <label class="settings-field__label">模型存储目录</label>
      <div class="settings-field__path-row">
        <input
          type="text"
          class="settings-field__input settings-field__input--path"
          :value="configStore.get('MODEL_DIR', '')"
          @change="updateField('MODEL_DIR', ($event.target as HTMLInputElement).value)"
          placeholder="留空使用默认路径 (./models)"
        />
      </div>
      <span class="settings-field__hint">Whisper 模型的本地存储路径</span>
    </div>

    <!-- 输出目录 -->
    <div class="settings-field">
      <label class="settings-field__label">默认输出目录</label>
      <div class="settings-field__path-row">
        <input
          type="text"
          class="settings-field__input settings-field__input--path"
          :value="configStore.get('OUTPUT_DIR', '')"
          @change="updateField('OUTPUT_DIR', ($event.target as HTMLInputElement).value)"
          placeholder="留空使用音频文件所在目录"
        />
      </div>
      <span class="settings-field__hint">生成的 LRC 文件的默认保存路径</span>
    </div>

    <!-- HF 镜像 -->
    <div class="settings-field">
      <label class="settings-field__label">HuggingFace 镜像</label>
      <div class="settings-field__path-row">
        <input
          type="text"
          class="settings-field__input settings-field__input--path"
          :value="configStore.get('HF_MIRROR', 'https://hf-mirror.com')"
          @change="updateField('HF_MIRROR', ($event.target as HTMLInputElement).value)"
          placeholder="https://hf-mirror.com"
        />
        <button
          class="settings-field__reset-btn"
          @click="updateField('HF_MIRROR', 'https://hf-mirror.com')"
          title="恢复默认镜像"
        >
          ↻
        </button>
      </div>
      <span class="settings-field__hint">下载模型时使用的镜像源地址，国内推荐 hf-mirror.com</span>
    </div>

    <!-- MSST 模型目录 -->
    <div class="settings-field">
      <label class="settings-field__label">人声分离模型目录</label>
      <div class="settings-field__path-row">
        <input
          type="text"
          class="settings-field__input settings-field__input--path"
          :value="configStore.get('MSST_MODEL_DIR', '')"
          @change="updateField('MSST_MODEL_DIR', ($event.target as HTMLInputElement).value)"
          placeholder="留空使用默认路径 (./models/msst_vocal)"
        />
      </div>
      <span class="settings-field__hint">MSST 人声分离模型的本地存储路径</span>
    </div>

    <!-- SSL 验证 -->
    <div class="settings-field">
      <label class="settings-field__check">
        <input
          type="checkbox"
          :checked="configStore.get('DISABLE_SSL_VERIFY', false)"
          @change="updateField('DISABLE_SSL_VERIFY', ($event.target as HTMLInputElement).checked)"
        />
        <span class="settings-field__label">跳过 SSL 证书验证</span>
      </label>
      <span class="settings-field__hint">下载模型时遇到 SSL 证书错误可尝试开启此选项</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useConfigStore } from '@/stores/configStore'

const configStore = useConfigStore()

async function updateField(key: string, value: any) {
  try {
    await configStore.updateConfig({ [key]: value })
  } catch (e: any) {
    console.error('配置更新失败:', e)
  }
}
</script>

<style scoped>
.path-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}
.settings-section__title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  padding-bottom: var(--space-sm);
  border-bottom: 1px solid var(--color-border-light);
}

.settings-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}
.settings-field__label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
}
.settings-field__hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.settings-field__path-row {
  display: flex;
  gap: var(--space-xs);
}
.settings-field__input {
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-input-bg);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  transition: border-color var(--transition-fast);
}
.settings-field__input:focus {
  border-color: var(--color-accent);
  outline: none;
}
.settings-field__input--path {
  flex: 1;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}
.settings-field__reset-btn {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--color-btn-secondary);
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}
.settings-field__reset-btn:hover {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}
.settings-field__check {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  cursor: pointer;
}
.settings-field__check input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-accent);
  cursor: pointer;
}
</style>
