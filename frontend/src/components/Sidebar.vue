<template>
  <aside class="sidebar">
    <h1>TLE-Tracking</h1>
    <nav>
      <router-link to="/" :class="{ active: $route.name === 'dashboard' }">仪表盘</router-link>
      <router-link to="/history" :class="{ active: $route.name === 'history' }">TLE 变化</router-link>
      <router-link to="/decay" :class="{ active: $route.name === 'decay' }">衰降状态</router-link>
    </nav>
    <div class="ws-box">
      <div class="ws-status">
        <span class="ws-dot" :class="connectionStatus"></span>
        <span class="ws-label">{{ statusLabel }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useWebSocket } from "../composables/useWebSocket"

const { connectionStatus } = useWebSocket()

const statusLabel = computed(() => ({
  connected: "已连接",
  connecting: "连接中",
  disconnected: "已断开",
}[connectionStatus.value]))
</script>

<style scoped>
.sidebar {
  width: 220px;
  background: #1e293b;
  padding: 1.5rem;
  border-right: 1px solid #334155;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}
.sidebar h1 {
  font-size: 1.1rem;
  margin-bottom: 2rem;
  color: #38bdf8;
  text-align: center;
}
.sidebar nav {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.sidebar a {
  color: #94a3b8;
  text-decoration: none;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  transition: all 0.15s;
}
.sidebar a:hover {
  background: #334155;
  color: #e2e8f0;
}
.sidebar a.active {
  background: #0ea5e9;
  color: #fff;
}
.ws-box {
  margin-top: auto;
  padding: 0 0.5rem;
}
.ws-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.5rem;
  font-size: 0.75rem;
  color: #94a3b8;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #0f172a;
}
.ws-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ws-dot.connected {
  background: #4ade80;
  box-shadow: 0 0 6px #4ade8044;
}
.ws-dot.connecting {
  background: #fbbf24;
  animation: pulse 1s ease-in-out infinite;
}
.ws-dot.disconnected {
  background: #f87171;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
