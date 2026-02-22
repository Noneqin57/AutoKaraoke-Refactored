<template>
  <div class="core-settings">
    <h3 class="settings-section__title">🎤 核心设置</h3>

    <!-- 语言 -->
    <div class="settings-field">
      <label class="settings-field__label">识别语言</label>
      <select
        class="settings-field__select"
        :value="configStore.get('LANGUAGE', 'ja')"
        @change="updateField('LANGUAGE', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="lang in configStore.languages" :key="lang.code" :value="lang.code">
          {{ lang.name }}
        </option>
      </select>
      <span class="settings-field__hint">设置 Whisper 识别的目标语言</span>
    </div>

    <!-- 模型大小 -->
    <div class="settings-field">
      <label class="settings-field__label">模型大小</label>
      <select
        class="settings-field__select"
        :value="configStore.get('MODEL_SIZE', 'large-v2')"
        @change="updateField('MODEL_SIZE', ($event.target as HTMLSelectElement).value)"
      >
        <option value="tiny">Tiny (~39 MB)</option>
        <option value="base">Base (~74 MB)</option>
        <option value="small">Small (~244 MB)</option>
        <option value="medium">Medium (~769 MB)</option>
        <option value="large-v2">Large-v2 (~1.5 GB) ⭐</option>
        <option value="large-v3">Large-v3 (~1.5 GB)</option>
      </select>
      <span class="settings-field__hint">越大精度越高，消耗更多显存</span>
    </div>

    <!-- 提示词 -->
    <div class="settings-field">
      <label class="settings-field__label">
        提示词
        <button class="settings-field__default-btn" @click="loadDefaultPrompt" title="加载当前语言的默认提示词">
          🔄 默认
        </button>
      </label>
      <textarea
        class="settings-field__textarea"
        :value="configStore.get('PROMPT', '')"
        @change="updateField('PROMPT', ($event.target as HTMLTextAreaElement).value)"
        placeholder="可选，提供给 Whisper 的上下文提示"
        rows="3"
      ></textarea>
      <span class="settings-field__hint">为 Whisper 提供上下文提示，可提高识别准确率</span>
    </div>

    <!-- 时间偏移 -->
    <div class="settings-field">
      <label class="settings-field__label">全局时间偏移 (ms)</label>
      <input
        type="number"
        class="settings-field__input"
        :value="configStore.get('OFFSET', 0)"
        @change="updateField('OFFSET', Number(($event.target as HTMLInputElement).value))"
        step="10"
      />
      <span class="settings-field__hint">正数延后，负数提前。单位毫秒</span>
    </div>

    <!-- 释放显存 -->
    <div class="settings-field settings-field--row">
      <label class="settings-field__label">完成后释放显存</label>
      <label class="settings-field__toggle">
        <input
          type="checkbox"
          :checked="configStore.get('RELEASE_VRAM', true)"
          @change="updateField('RELEASE_VRAM', ($event.target as HTMLInputElement).checked)"
        />
        <span class="settings-field__toggle-slider"></span>
      </label>
      <span class="settings-field__hint">任务完成后卸载模型以释放 GPU 显存</span>
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

async function loadDefaultPrompt() {
  if (Object.keys(configStore.promptDefaults).length === 0) {
    await configStore.loadPromptDefaults()
  }
  const lang = configStore.get('LANGUAGE', 'ja')
  const defaultPrompt = configStore.promptDefaults[lang] || configStore.promptDefaults['default'] || ''
  updateField('PROMPT', defaultPrompt)
}
</script>

<style scoped>
.core-settings {
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
.settings-field--row {
  flex-direction: row;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-sm);
}
.settings-field--row .settings-field__hint {
  width: 100%;
}
.settings-field__label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}
.settings-field__default-btn {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--color-btn-secondary);
  color: var(--color-text-secondary);
  transition: all var(--transition-fast);
}
.settings-field__default-btn:hover {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}
.settings-field__hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
.settings-field__select,
.settings-field__input {
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-input-bg);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  transition: border-color var(--transition-fast);
}
.settings-field__select:focus,
.settings-field__input:focus {
  border-color: var(--color-accent);
  outline: none;
}
.settings-field__textarea {
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-input-bg);
  color: var(--color-text);
  font-size: var(--font-size-sm);
  font-family: var(--font-mono);
  resize: vertical;
  transition: border-color var(--transition-fast);
}
.settings-field__textarea:focus {
  border-color: var(--color-accent);
  outline: none;
}
.settings-field__input[type="number"] {
  max-width: 200px;
}

/* Toggle Switch */
.settings-field__toggle {
  position: relative;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}
.settings-field__toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}
.settings-field__toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--color-border);
  border-radius: 24px;
  transition: all var(--transition-fast);
}
.settings-field__toggle-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: transform var(--transition-fast);
}
.settings-field__toggle input:checked + .settings-field__toggle-slider {
  background: var(--color-accent);
}
.settings-field__toggle input:checked + .settings-field__toggle-slider::before {
  transform: translateX(20px);
}
</style>
