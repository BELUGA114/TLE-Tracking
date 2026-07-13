<template>
  <div>
    <h2 class="page-title">衰降状态</h2>

    <template v-if="satellites.length">
      <div class="cards cards-2 chart-row">
        <div class="card">
          <h3 class="chart-title">阶段分布</h3>
          <PhasePieChart :satellites="satellites" />
        </div>
        <div class="card">
          <h3 class="chart-title">近地点/远地点分布</h3>
          <PhaseScatterChart :satellites="satellites" />
        </div>
      </div>

      <div class="cards cards-2">
        <div v-for="sat in satellites" :key="sat.norad" class="card">
          <div class="card-header">
            <h3>#{{ sat.norad }} {{ sat.name }}</h3>
            <span :class="phaseClass(sat.phase)">{{ phaseLabel(sat.phase) }}</span>
          </div>
          <div class="card-body">
            <div class="stat">
              <div class="stat-label">近地点</div>
              <div class="stat-value">{{ sat.periapsis != null ? sat.periapsis.toFixed(1) : "-" }} km</div>
            </div>
            <div class="stat">
              <div class="stat-label">远地点</div>
              <div class="stat-value">{{ sat.apoapsis != null ? sat.apoapsis.toFixed(1) : "-" }} km</div>
            </div>
          </div>
        </div>
      </div>
    </template>
    <div v-else class="empty-card">
      <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1" width="48" height="48" style="opacity:0.3;margin-bottom:1rem;">
        <circle cx="24" cy="24" r="20" stroke-dasharray="4 3" />
        <circle cx="24" cy="24" r="5" fill="currentColor" opacity="0.3" />
      </svg>
      <p>暂无衰降状态数据</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import PhasePieChart from "../components/PhasePieChart.vue"
import PhaseScatterChart from "../components/PhaseScatterChart.vue"
import { useWebSocket } from "../composables/useWebSocket"

const { decaySatellites: satellites } = useWebSocket()

function phaseClass(phase: string) {
  const map: Record<string, string> = {
    normal: "tag tag-initial",
    early_decay: "tag tag-correction",
    accelerating: "tag tag-maneuver",
    critical: "tag tag-critical",
  }
  return map[phase] || "tag"
}

function phaseLabel(phase: string) {
  const map: Record<string, string> = {
    normal: "正常",
    early_decay: "早期衰降",
    accelerating: "加速衰降",
    critical: "临界",
  }
  return map[phase] || phase
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.card-header h3 {
  margin-bottom: 0;
}
.card-body {
  margin-top: 0.75rem;
  display: flex;
  gap: 2rem;
}
.stat-label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}
.stat-value {
  font-family: var(--font-mono);
  font-size: 1.2rem;
  font-weight: 500;
  color: var(--color-signal-cyan);
}
.chart-row {
  margin-bottom: var(--space-xl);
}
</style>
