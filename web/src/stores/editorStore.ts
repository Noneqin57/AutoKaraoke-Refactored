/**
 * 编辑器 Store
 *
 * 包含 LRC 解析逻辑：行级 [MM:SS.xx] 和逐字 <MM:SS.xx> / [MM:SS.xx] 标签。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { parseTime } from '@/utils/time'

export interface LrcLine {
    index: number
    startTime: number
    endTime: number
    text: string
    translation: string
    words: LrcWord[]
}

export interface LrcWord {
    text: string
    startTime: number
    endTime: number
}

/** 解析尖括号逐字标签 "<MM:SS.xx>text<MM:SS.xx>text..." */
function parseAngleBracketWordTags(content: string): LrcWord[] {
    const wordRegex = /<(\d+:\d+\.\d+)>([^<]*)/g
    const words: LrcWord[] = []
    let match: RegExpExecArray | null

    while ((match = wordRegex.exec(content)) !== null) {
        const startTime = parseTime(match[1]!)
        const text = match[2]!
        if (text) {
            words.push({ text, startTime, endTime: startTime })
        }
    }

    // 设置 endTime 为下一个 word 的 startTime
    for (let i = 0; i < words.length - 1; i++) {
        words[i]!.endTime = words[i + 1]!.startTime
    }

    return words
}

/** 解析方括号逐字标签 "[MM:SS.xx]text[MM:SS.xx]text..." (PyQt 输出格式) */
function parseSquareBracketWordTags(content: string, lineStartTime: number): LrcWord[] {
    // 分割为 [timestamp] 和文本交替
    const parts = content.split(/(\[\d+:\d+\.\d+\])/)
    const words: LrcWord[] = []
    let currentTime = lineStartTime

    for (const part of parts) {
        if (!part) continue
        const tsMatch = part.match(/^\[(\d+:\d+\.\d+)\]$/)
        if (tsMatch) {
            currentTime = parseTime(tsMatch[1]!)
        } else {
            // 每个字符单独作为一个 word
            for (const char of part) {
                if (char.trim() || char === ' ') {
                    words.push({ text: char, startTime: currentTime, endTime: currentTime })
                }
            }
        }
    }

    // 设置 endTime 为下一个 word 的 startTime
    for (let i = 0; i < words.length - 1; i++) {
        words[i]!.endTime = words[i + 1]!.startTime
    }

    return words
}

/** 解析完整 LRC 内容 */
function parseLrc(content: string): LrcLine[] {
    const lines: LrcLine[] = []
    const rawLines = content.split(/\r?\n/)
    const lineRegex = /^\[(\d+:\d+\.\d+)\](.*)/

    for (const rawLine of rawLines) {
        const match = rawLine.match(lineRegex)
        if (!match) continue

        const startTime = parseTime(match[1]!)
        const rest = match[2]!

        // 检查是否包含逐字标签（尖括号或方括号）
        const hasAngleTags = /<\d+:\d+\.\d+>/.test(rest)
        const hasSquareTags = /\[\d+:\d+\.\d+\]/.test(rest)
        let text = ''
        let words: LrcWord[] = []

        if (hasAngleTags) {
            words = parseAngleBracketWordTags(rest)
            text = words.map(w => w.text).join('')
        } else if (hasSquareTags) {
            words = parseSquareBracketWordTags(rest, startTime)
            text = words.map(w => w.text).join('')
        } else {
            text = rest.trim()
        }

        // 跳过空文本行（间奏标记），但用其时间戳更新上一行的 endTime
        if (!text) {
            if (lines.length > 0) {
                lines[lines.length - 1]!.endTime = startTime
            }
            continue
        }

        // 检查是否是上一行的翻译（时间戳相同）
        if (lines.length > 0) {
            const lastLine = lines[lines.length - 1]!
            // 允许 50ms 误差
            if (Math.abs(lastLine.startTime - startTime) < 0.05) {
                if (lastLine.translation) {
                    lastLine.translation += ' ' + text
                } else {
                    lastLine.translation = text
                }
                continue // 跳过添加新行，合并到上一行
            }
        }

        lines.push({
            index: lines.length,
            startTime,
            endTime: startTime,
            text,
            translation: '',
            words,
        })
    }

    // 设置每行的 endTime 为下一行的 startTime
    for (let i = 0; i < lines.length - 1; i++) {
        lines[i]!.endTime = lines[i + 1]!.startTime
    }
    // 最后一行处理
    if (lines.length > 0) {
        const last = lines[lines.length - 1]!
        if (last.words.length > 0) {
            const lastWord = last.words[last.words.length - 1]!
            last.endTime = lastWord.endTime > lastWord.startTime ? lastWord.endTime : last.startTime + 5
        } else {
            last.endTime = last.startTime + 5
        }
    }

    return lines
}

export const useEditorStore = defineStore('editor', () => {
    const lrcContent = ref('')
    const lines = ref<LrcLine[]>([])
    const selectedLineIndex = ref(-1)
    const isDirty = ref(false)

    function setContent(content: string) {
        lrcContent.value = content
        lines.value = parseLrc(content)
        selectedLineIndex.value = lines.value.length > 0 ? 0 : -1
        isDirty.value = false
    }

    function updateLine(index: number, updates: Partial<LrcLine>) {
        if (index >= 0 && index < lines.value.length) {
            const line = lines.value[index]!
            lines.value[index] = { ...line, ...updates } as LrcLine
            isDirty.value = true
        }
    }

    function reset() {
        lrcContent.value = ''
        lines.value = []
        selectedLineIndex.value = -1
        isDirty.value = false
    }

    return {
        lrcContent, lines, selectedLineIndex, isDirty,
        setContent, updateLine, reset,
    }
})
