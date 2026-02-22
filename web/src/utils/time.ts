/** 将秒数格式化为 "MM:SS.xx" */
export function formatMs(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  const ms = Math.round((seconds % 1) * 100)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`
}

/**
 * 解析 "MM:SS.xx" / "MM:SS.xxx" 时间字符串为秒数
 *
 * 统一实现：根据小数部分长度自动适配精度。
 * - 2位: 视为百分秒 (01:23.45 → 83.45s)
 * - 3位: 视为毫秒 (01:23.456 → 83.456s)
 * - 其他: 按 10^n 计算
 */
export function parseTime(str: string): number {
  const match = str.match(/^(\d+):(\d+)\.(\d+)$/)
  if (!match) return 0
  const m = parseInt(match[1]!)
  const s = parseInt(match[2]!)
  const frac = match[3]!
  const ms = parseInt(frac) / Math.pow(10, frac.length)
  return m * 60 + s + ms
}
