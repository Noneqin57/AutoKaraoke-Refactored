/**
 * WebSocket 封装组合式函数
 */
import { ref, onUnmounted } from 'vue'

export type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface UseWebSocketOptions {
    /** 自动重连 */
    autoReconnect?: boolean
    /** 重连间隔（ms） */
    reconnectInterval?: number
    /** 最大重连次数 */
    maxReconnects?: number
    /** 消息回调 */
    onMessage?: (data: any) => void
    /** 连接成功回调 */
    onConnected?: () => void
    /** 断开回调 */
    onDisconnected?: () => void
}

export function useWebSocket(url: string, options: UseWebSocketOptions = {}) {
    const {
        autoReconnect = true,
        reconnectInterval = 3000,
        maxReconnects = 10,
        onMessage,
        onConnected,
        onDisconnected,
    } = options

    const status = ref<WsStatus>('disconnected')
    let ws: WebSocket | null = null
    let reconnectCount = 0
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let isDestroyed = false

    function getWsUrl(): string {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const host = window.location.host
        return `${protocol}//${host}${url}`
    }

    function clearReconnectTimer() {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer)
            reconnectTimer = null
        }
    }

    function connect() {
        if (isDestroyed) return
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            return
        }

        // 连接前清除残留重连定时器
        clearReconnectTimer()

        status.value = 'connecting'
        ws = new WebSocket(getWsUrl())

        ws.onopen = () => {
            status.value = 'connected'
            reconnectCount = 0
            // 连接成功后清除重连定时器
            clearReconnectTimer()
            onConnected?.()
        }

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)
                onMessage?.(data)
            } catch {
                // 非 JSON 消息忽略
            }
        }

        ws.onclose = () => {
            status.value = 'disconnected'
            onDisconnected?.()
            if (!isDestroyed && autoReconnect && reconnectCount < maxReconnects) {
                reconnectTimer = setTimeout(() => {
                    reconnectTimer = null
                    reconnectCount++
                    connect()
                }, reconnectInterval)
            }
        }

        ws.onerror = () => {
            status.value = 'error'
        }
    }

    function disconnect() {
        isDestroyed = true
        clearReconnectTimer()
        reconnectCount = maxReconnects // 防止重连
        ws?.close()
        ws = null
        status.value = 'disconnected'
    }

    function send(data: any) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(typeof data === 'string' ? data : JSON.stringify(data))
        }
    }

    onUnmounted(() => {
        disconnect()
    })

    return {
        status,
        connect,
        disconnect,
        send,
    }
}
