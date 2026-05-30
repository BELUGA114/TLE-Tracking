import { ref, onMounted, onUnmounted } from "vue"
import type { Satellite, DecaySatellite, HistoryRecord } from "../types"

// 模块级单例状态 —— 所有调用 useWebSocket() 的组件共享同一份数据
const satellites = ref<Satellite[]>([])
const historyRecords = ref<HistoryRecord[]>([])
const decaySatellites = ref<DecaySatellite[]>([])
const loading = ref(true)

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let refCount = 0

function connect() {
  if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) return

  const protocol = location.protocol === "https:" ? "wss:" : "ws:"
  ws = new WebSocket(`${protocol}//${location.host}/api/ws`)

  ws.onmessage = (event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data)
      switch (msg.type) {
        case "satellites":
          satellites.value = msg.data.satellites
          break
        case "history":
          historyRecords.value = msg.data.changes
          break
        case "decay":
          decaySatellites.value = msg.data.satellites
          break
      }
      loading.value = false
    } catch {
      // ignore parse errors
    }
  }

  ws.onclose = () => {
    ws = null
    scheduleReconnect()
  }

  ws.onerror = () => {
    ws?.close()
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connect()
  }, 3000)
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
}

export function useWebSocket() {
  onMounted(() => {
    refCount++
    connect()
  })

  onUnmounted(() => {
    refCount--
    if (refCount <= 0) {
      disconnect()
    }
  })

  return { satellites, historyRecords, decaySatellites, loading }
}
