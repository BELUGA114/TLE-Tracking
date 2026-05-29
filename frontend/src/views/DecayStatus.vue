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
    <div v-else class="card empty-card">
      <p>暂无衰降状态数据</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import type { DecaySatellite } from "../types"
import { fetchDecayStatus } from "../api"
import PhasePieChart from "../components/PhasePieChart.vue"
import PhaseScatterChart from "../components/PhaseScatterChart.vue"

const satellites = ref<DecaySatellite[]>([])

onMounted(async () => {
  try {
    const data = await fetchDecayStatus()
    satellites.value = data.satellites
  } catch (e) {
    console.error("加载衰降状态失败", e)
  }
})

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
.tag-critical {
  background: #7f1d1d;
  color: #fca5a5;
}
.card-body {
  margin-top: 0.75rem;
  display: flex;
  gap: 2rem;
}
.stat-label {
  font-size: 0.75rem;
  color: #64748b;
}
.stat-value {
  font-size: 1.2rem;
}
.empty-card {
  text-align: center;
  padding: 3rem;
  color: #64748b;
}
.chart-row {
  margin-bottom: 1.5rem;
}
.chart-title {
  font-size: 0.9rem;
  color: #94a3b8;
  margin-bottom: 0.25rem;
}
</style>
