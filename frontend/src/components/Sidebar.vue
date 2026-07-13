<template>
  <aside class="sidebar">
    <div class="brand">
      <svg class="brand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="3" fill="currentColor" />
        <ellipse cx="12" cy="12" rx="10" ry="5" transform="rotate(-30 12 12)" />
        <ellipse cx="12" cy="12" rx="10" ry="5" transform="rotate(60 12 12)" />
      </svg>
      <span class="brand-text">TLE-Tracking</span>
    </div>

    <nav>
      <router-link to="/" :class="{ active: $route.name === 'dashboard' }">
        <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="1" y="1" width="6" height="6" rx="1" />
          <rect x="11" y="1" width="6" height="6" rx="1" />
          <rect x="1" y="11" width="6" height="6" rx="1" />
          <rect x="11" y="11" width="6" height="6" rx="1" />
        </svg>
        <span>仪表盘</span>
      </router-link>

      <router-link to="/history" :class="{ active: $route.name === 'history' }">
        <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="9" cy="9" r="7.5" />
          <polyline points="9,4.5 9,9 12.5,10.5" />
        </svg>
        <span>TLE 变化</span>
      </router-link>

      <router-link to="/decay" :class="{ active: $route.name === 'decay' }">
        <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M9 1.5L16.5 15H1.5L9 1.5Z" />
          <line x1="9" y1="7" x2="9" y2="10.5" />
          <circle cx="9" cy="13" r="0.6" fill="currentColor" />
        </svg>
        <span>衰降状态</span>
      </router-link>

      <router-link to="/settings" :class="{ active: $route.name === 'settings' }">
        <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="9" cy="9" r="3" />
          <path d="M9 1.5v2M9 14.5v2M1.5 9h2M14.5 9h2M3.7 3.7l1.4 1.4M12.9 12.9l1.4 1.4M3.7 14.3l1.4-1.4M12.9 5.1l1.4-1.4" />
        </svg>
        <span>设置</span>
      </router-link>
    </nav>

    <div class="ws-box">
      <div class="ws-status" :class="connectionStatus">
        <span class="ws-dot"></span>
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
  height: 100vh;
  position: sticky;
  top: 0;
  background: var(--color-void);
  border-right: 1px solid var(--color-border);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: var(--space-xl) var(--space-lg);
  z-index: var(--z-sidebar);
}

/* ==== 品牌区 ==== */
.brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-xl);
  padding-bottom: var(--space-lg);
  border-bottom: 1px solid var(--color-border);
}
.brand-icon {
  width: 28px;
  height: 28px;
  color: var(--color-signal-gold);
}
.brand-text {
  font-family: var(--font-heading);
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--color-text-primary);
}

/* ==== 导航 ==== */
nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
nav a {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  color: var(--color-text-secondary);
  text-decoration: none;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-md);
  border-left: 2px solid transparent;
  transition: all var(--transition-fast);
}
nav a svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}
nav a:hover {
  background: rgba(245, 158, 11, 0.06);
  color: var(--color-text-primary);
}
nav a.active {
  background: rgba(245, 158, 11, 0.08);
  color: var(--color-signal-gold);
  border-left-color: var(--color-signal-gold);
}

/* ==== WebSocket 指示器 ==== */
.ws-box {
  margin-top: auto;
}
.ws-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.4rem;
  font-size: 0.72rem;
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}
.ws-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ws-status.connected .ws-dot {
  background: var(--color-nominal-green);
  box-shadow: 0 0 8px rgba(74, 222, 128, 0.4);
}
.ws-status.connecting .ws-dot {
  background: var(--color-warning-orange);
  animation: pulse 1s ease-in-out infinite;
}
.ws-status.disconnected .ws-dot {
  background: var(--color-critical-red);
}
.ws-status.connected .ws-label {
  color: var(--color-nominal-green);
}
.ws-status.disconnected .ws-label {
  color: var(--color-critical-red);
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.35; }
}
</style>
