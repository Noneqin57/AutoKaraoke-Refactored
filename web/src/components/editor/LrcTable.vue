<template>
  <div class="lrc-table-wrapper">
    <table class="lrc-table">
      <thead>
        <tr>
          <th class="lrc-table__col-idx">#</th>
          <th class="lrc-table__col-time">开始</th>
          <th class="lrc-table__col-time">结束</th>
          <th class="lrc-table__col-text">歌词</th>
          <th class="lrc-table__col-trans">翻译</th>
          <th class="lrc-table__col-actions">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(line, i) in lines"
          :key="i"
          class="lrc-table__row"
          :class="{
            'lrc-table__row--active': i === activeIndex,
            'lrc-table__row--selected': i === selectedIndex
          }"
          @click="$emit('select', i)"
          @dblclick="$emit('seek-to', line.startTime)"
        >
          <td class="lrc-table__col-idx">{{ i + 1 }}</td>
          <td class="lrc-table__col-time">
            <input
              type="text"
              :value="formatMs(line.startTime)"
              @change="(e) => updateTime(i, 'startTime', e)"
              @focus="$emit('select', i)"
              class="lrc-table__time-input"
            />
          </td>
          <td class="lrc-table__col-time">
            <input
              type="text"
              :value="formatMs(line.endTime)"
              @change="(e) => updateTime(i, 'endTime', e)"
              @focus="$emit('select', i)"
              class="lrc-table__time-input"
            />
          </td>
          <td class="lrc-table__col-text">
            <input
              type="text"
              :value="line.text"
              @change="(e) => updateText(i, e)"
              @focus="$emit('select', i)"
              class="lrc-table__text-input"
            />
          </td>
          <td class="lrc-table__col-trans">
            <input
              type="text"
              :value="line.translation"
              @change="(e) => updateTranslation(i, e)"
              @focus="$emit('select', i)"
              class="lrc-table__text-input lrc-table__text-input--trans"
              placeholder="—"
            />
          </td>
          <td class="lrc-table__col-actions">
            <button
              class="lrc-table__action-btn"
              @click.stop="$emit('set-time', i)"
              title="将开始时间设为当前播放位置"
            >
              ⏱️
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { LrcLine } from '@/stores/editorStore'
import { formatMs, parseTime } from '@/utils/time'

const props = defineProps<{
  lines: LrcLine[]
  activeIndex: number
  selectedIndex: number
}>()

const emit = defineEmits<{
  select: [index: number]
  'seek-to': [time: number]
  'set-time': [index: number]
  'update-line': [index: number, updates: Partial<LrcLine>]
}>()

function updateTime(index: number, field: 'startTime' | 'endTime', e: Event) {
  const val = (e.target as HTMLInputElement).value
  const t = parseTime(val)
  emit('update-line', index, { [field]: t })
}

function updateText(index: number, e: Event) {
  emit('update-line', index, { text: (e.target as HTMLInputElement).value })
}

function updateTranslation(index: number, e: Event) {
  emit('update-line', index, { translation: (e.target as HTMLInputElement).value })
}
</script>

<style scoped>
.lrc-table-wrapper {
  flex: 1;
  overflow-y: auto;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  background: var(--color-card-bg);
}
.lrc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}
.lrc-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--color-bg-secondary);
}
.lrc-table th {
  padding: var(--space-sm) var(--space-sm);
  text-align: left;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--color-border-light);
}
.lrc-table__row {
  cursor: pointer;
  transition: background var(--transition-fast);
}
.lrc-table__row:hover {
  background: var(--color-bg-secondary);
}
.lrc-table__row--active {
  background: var(--color-accent-soft) !important;
}
.lrc-table__row--selected {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}
.lrc-table td {
  padding: var(--space-xs) var(--space-sm);
  border-bottom: 1px solid var(--color-border-light);
  vertical-align: middle;
}
.lrc-table__col-idx {
  width: 40px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
}
.lrc-table__col-time {
  width: 90px;
}
.lrc-table__col-actions {
  width: 70px;
  text-align: center;
}
.lrc-table__time-input {
  width: 100%;
  padding: 3px 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  transition: all var(--transition-fast);
}
.lrc-table__time-input:focus {
  border-color: var(--color-accent);
  background: var(--color-input-bg);
  outline: none;
}
.lrc-table__text-input {
  width: 100%;
  padding: 3px 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text);
  font-size: var(--font-size-sm);
  font-weight: 500;
  transition: all var(--transition-fast);
}
.lrc-table__row--active .lrc-table__text-input:not(.lrc-table__text-input--trans) {
  font-weight: 700;
  color: var(--color-accent);
}
.lrc-table__text-input:focus {
  border-color: var(--color-accent);
  background: var(--color-input-bg);
  outline: none;
}
.lrc-table__text-input--trans {
  color: var(--color-text-secondary);
  font-weight: normal;
}
.lrc-table__text-input::placeholder {
  color: var(--color-text-tertiary);
}
.lrc-table__action-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: transparent;
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background var(--transition-fast);
}
.lrc-table__action-btn:hover {
  background: var(--color-bg-tertiary);
}
</style>
