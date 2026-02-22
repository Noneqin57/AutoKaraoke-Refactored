/**
 * 类型化 API 客户端
 */

const BASE_URL = ''  // 开发环境由 Vite 代理

// ============ 通用请求 ============
async function request<T>(url: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BASE_URL}${url}`, {
        headers: { 'Content-Type': 'application/json', ...options?.headers },
        ...options,
    })
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || `HTTP ${res.status}`)
    }
    return res.json()
}

// ============ 配置 ============
export interface ConfigData {
    config: Record<string, any>
}

export interface LanguageItem {
    code: string
    name: string
}

export const configApi = {
    get: () => request<ConfigData>('/api/config'),
    update: (updates: Record<string, any>) =>
        request<ConfigData>('/api/config', {
            method: 'PUT',
            body: JSON.stringify({ updates }),
        }),
    getLanguages: () =>
        request<{ languages: LanguageItem[] }>('/api/config/languages'),
    getPromptDefaults: () =>
        request<Record<string, string>>('/api/config/prompt_defaults'),
}

// ============ 文件 ============
export interface FileUploadResponse {
    file_id: string
    filename: string
    size: number
}

export interface LyricsParseResponse {
    clean_text: string
    headers: string[]
    lines_text: string[]
    translations: Record<string, string[]>
    timestamps: number[]
    raw_content: string
}

export const fileApi = {
    uploadAudio: async (file: File): Promise<FileUploadResponse> => {
        const formData = new FormData()
        formData.append('file', file)
        const res = await fetch('/api/file/upload/audio', {
            method: 'POST',
            body: formData,
        })
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }))
            throw new Error(err.detail || `HTTP ${res.status}`)
        }
        return res.json()
    },

    uploadLyrics: async (file: File): Promise<LyricsParseResponse> => {
        const formData = new FormData()
        formData.append('file', file)
        const res = await fetch('/api/file/upload/lyrics', {
            method: 'POST',
            body: formData,
        })
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }))
            throw new Error(err.detail || `HTTP ${res.status}`)
        }
        return res.json()
    },

    downloadLrc: async (content: string, encoding: string, filename: string) => {
        const res = await fetch('/api/file/download/lrc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, encoding, filename }),
        })
        if (!res.ok) throw new Error('下载失败')
        const blob = await res.blob()
        // 触发下载
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        a.click()
        URL.revokeObjectURL(url)
    },
}

// ============ 任务 ============
export interface TaskStartRequest {
    audio_file_id: string
    lyrics_text: string
    raw_lrc_content: string
    enable_force_calibration: boolean
    enable_avg_distribution: boolean
    enable_msst: boolean
    msst_model_key: string
}

export const taskApi = {
    start: (req: TaskStartRequest) =>
        request<{ status: string; message: string }>('/api/task/start', {
            method: 'POST',
            body: JSON.stringify(req),
        }),
    stop: () =>
        request<{ status: string; message: string }>('/api/task/stop', {
            method: 'POST',
        }),
}

// ============ 模型 ============
export interface ModelItem {
    name: string
    type: string
    key: string
    repo_id_or_url: string
    local_path: string
    size_mb: number
    is_downloaded: boolean
}

export const modelApi = {
    list: () => request<{ models: ModelItem[] }>('/api/model/list'),
    download: (key: string, type: string) =>
        request<{ status: string }>('/api/model/download', {
            method: 'POST',
            body: JSON.stringify({ key, type }),
        }),
    stopDownload: (key: string, type: string) =>
        request<{ status: string }>('/api/model/download/stop', {
            method: 'POST',
            body: JSON.stringify({ key, type }),
        }),
    delete: (key: string, type: string) =>
        request<{ status: string }>(`/api/model/${key}/${type}`, {
            method: 'DELETE',
        }),
}

// ============ 音频 URL ============
export function getAudioUrl(fileId: string): string {
    return `/api/audio/${fileId}`
}

// ============ MSST 人声分离模型 ============
export interface MsstModelItem {
    key: string
    name: string
    model_type: string
    size_mb: number
    is_downloaded: boolean
}

export const msstApi = {
    list: () => request<{ models: MsstModelItem[] }>('/api/msst/list'),
}

// ============ 批量处理 ============
export interface BatchItemRequest {
    audio_file_id: string
    lyrics_text: string
    raw_content: string
    name: string
}

export interface BatchStartRequest {
    items: BatchItemRequest[]
    enable_force_calibration: boolean
    enable_avg_distribution: boolean
    enable_msst: boolean
    msst_model_key: string
}

export const batchApi = {
    start: (req: BatchStartRequest) =>
        request<{ status: string; message: string }>('/api/batch/start', {
            method: 'POST',
            body: JSON.stringify(req),
        }),
    stop: () =>
        request<{ status: string; message: string }>('/api/batch/stop', {
            method: 'POST',
        }),
    downloadAll: async () => {
        const res = await fetch('/api/batch/download-all')
        if (!res.ok) throw new Error('下载失败')
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'batch_results.zip'
        a.click()
        URL.revokeObjectURL(url)
    },
    downloadSingle: async (index: number, name: string) => {
        const res = await fetch(`/api/batch/download/${index}`)
        if (!res.ok) throw new Error('下载失败')
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${name}.lrc`
        a.click()
        URL.revokeObjectURL(url)
    },
}
