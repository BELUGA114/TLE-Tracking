<script setup lang="ts">
import { computed } from "vue"
import VChart from "vue-echarts"
import "../echarts"
import type { DecaySatellite } from "../types"

const props = defineProps<{
  satellites: DecaySatellite[]
}>()

const PHASES: Record<string, { label: string; color: string }> = {
  normal: { label: "正常", color: "#4ade80" },
  early_decay: { label: "早期衰降", color: "#fbbf24" },
  accelerating: { label: "加速衰降", color: "#fb923c" },
  critical: { label: "临界", color: "#f87171" },
}

const option = computed(() => {
  const counts: Record<string, number> = {}
  for (const s of props.satellites) {
    counts[s.phase] = (counts[s.phase] || 0) + 1
  }

  const data = Object.entries(counts).map(([phase, count]) => ({
    value: count,
    name: PHASES[phase]?.label ?? phase,
    itemStyle: { color: PHASES[phase]?.color ?? "#64748b" },
  }))

  return {
    tooltip: {
      trigger: "item",
      backgroundColor: "#1e293b",
      borderColor: "#334155",
      textStyle: { color: "#e2e8f0", fontSize: 12 },
      formatter: "{b}: {c} ({d}%)",
    },
    series: [
      {
        type: "pie",
        radius: ["45%", "70%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: true,
        label: {
          show: true,
          formatter: "{b}\n{d}%",
          color: "#94a3b8",
          fontSize: 12,
        },
        labelLine: {
          lineStyle: { color: "#334155" },
        },
        data,
      },
    ],
  }
})
</script>

<template>
  <VChart class="chart" :option="option" autoresize />
</template>

<style scoped>
.chart {
  width: 100%;
  height: 260px;
}
</style>
