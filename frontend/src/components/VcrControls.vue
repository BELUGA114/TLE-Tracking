<template>
  <div class="vcr-overlay" v-if="isReady">
    <div class="vcr-bar">
      <div class="vcr-time">{{ timeDisplay }}</div>

      <div class="vcr-timeline">
        <input
          type="range"
          class="vcr-slider"
          :min="-rangeMinutes"
          :max="rangeMinutes"
          :value="offsetMinutes"
          @input="onSeek"
          step="1"
        />
        <span class="vcr-offset">{{ offsetLabel }}</span>
      </div>

      <div class="vcr-controls">
        <button
          class="vcr-btn"
          title="重置到实时"
          :disabled="!isPaused && propRate === 1 && offsetMinutes === 0"
          @click="$emit('reset')"
        >
          ⟳
        </button>
        <button class="vcr-btn vcr-btn-play" title="播放/暂停" @click="$emit('togglePause')">
          {{ isPaused ? "▶" : "⏸" }}
        </button>
        <div class="vcr-speed-group">
          <button
            v-for="s in speeds"
            :key="s"
            class="vcr-btn vcr-speed"
            :class="{ active: propRate === s && !isPaused }"
            @click="$emit('update:propRate', s)"
          >
            {{ s }}×
          </button>
        </div>
      </div>
      <div v-if="isFallback" class="vcr-fallback" title="WebGPU 不可用，使用 CPU 传播">CPU</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{
  simTime: Date
  isPaused: boolean
  propRate: number
  isReady: boolean
  isFallback: boolean
}>()

const emit = defineEmits<{
  "update:propRate": [rate: number]
  togglePause: []
  reset: []
  seek: [offsetMs: number]
}>()

const speeds = [0.5, 1, 2, 10, 50]
const rangeMinutes = 1440

const timeDisplay = computed(() => {
  try {
    return (props.simTime as Date)
      .toISOString()
      .replace("T", " ")
      .replace(/\.\d{3}Z$/, " UTC")
  } catch {
    return "—"
  }
})

const offsetMinutes = computed(() => {
  return Math.round((props.simTime.getTime() - Date.now()) / 60000)
})

const offsetLabel = computed(() => {
  const m = offsetMinutes.value
  if (Math.abs(m) <= 1) return "实时"
  const absM = Math.abs(m)
  const h = Math.floor(absM / 60)
  const min = absM % 60
  const sign = m < 0 ? "-" : "+"
  if (h > 0) return `${sign}${h}h ${min}m`
  return `${sign}${min}m`
})

function onSeek(e: Event) {
  const target = e.target as HTMLInputElement
  const minutes = parseInt(target.value)
  emit("seek", minutes * 60000)
}
</script>

<style scoped>
.vcr-overlay {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--z-overlay);
  pointer-events: none;
  width: 90%;
  max-width: 850px;
}
.vcr-bar {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  background: rgba(10, 22, 40, 0.92);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 0.35rem 0.75rem;
  backdrop-filter: blur(10px);
  pointer-events: auto;
}
.vcr-time {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  color: var(--color-signal-gold);
  white-space: nowrap;
  min-width: 13em;
  text-align: center;
}
.vcr-timeline {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex: 1;
}
.vcr-slider {
  -webkit-appearance: none;
  appearance: none;
  flex: 1;
  height: 3px;
  background: var(--color-border);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.vcr-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-signal-cyan);
  border: 2px solid #0891b2;
  cursor: pointer;
  box-shadow: 0 0 6px rgba(34, 211, 238, 0.4);
  transition: transform 0.1s;
}
.vcr-slider::-webkit-slider-thumb:hover {
  transform: scale(1.25);
}
.vcr-slider::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-signal-cyan);
  border: 2px solid #0891b2;
  cursor: pointer;
}
.vcr-offset {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--color-text-muted);
  min-width: 4em;
  text-align: right;
  white-space: nowrap;
}
.vcr-controls {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.vcr-btn {
  background: transparent;
  border: 1px solid var(--color-border);
  color: #cbd5e1;
  border-radius: var(--radius-sm);
  padding: 0.2rem 0.5rem;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.1s;
  line-height: 1.4;
}
.vcr-btn:hover {
  background: var(--color-surface-raised);
  color: var(--color-text-primary);
  border-color: var(--color-signal-gold);
}
.vcr-btn:disabled {
  opacity: 0.35;
  cursor: default;
}
.vcr-btn-play {
  font-size: 0.9rem;
  padding: 0.2rem 0.6rem;
}
.vcr-speed-group {
  display: flex;
  gap: 2px;
}
.vcr-speed {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  padding: 0.15rem 0.35rem;
  min-width: 2.2em;
  text-align: center;
}
.vcr-speed.active {
  background: var(--color-signal-gold);
  border-color: var(--color-signal-gold);
  color: var(--color-space-black);
}
.vcr-fallback {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  background: rgba(251, 146, 60, 0.12);
  color: var(--color-warning-orange);
  border: 1px solid rgba(251, 146, 60, 0.35);
  border-radius: var(--radius-sm);
  padding: 0.1rem 0.4rem;
  font-weight: 600;
}
</style>
