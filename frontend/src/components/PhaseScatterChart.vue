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
  const dataMap: Record<string, [number, number][]> = {
    normal: [],
    early_decay: [],
    accelerating: [],
    critical: [],
  }

  for (const s of props.satellites) {
    if (s.periapsis != null && s.apoapsis != null) {
      const key = s.phase in dataMap ? s.phase : "normal"
      dataMap[key].push([s.periapsis, s.apoapsis])
    }
  }

  const series = Object.entries(dataMap)
    .filter(([, points]) => points.length > 0)
    .map(([phase, points]) => ({
      name: PHASES[phase]?.label ?? phase,
      type: "scatter" as const,
      data: points,
      symbolSize: 8,
      itemStyle: { color: PHASES[phase]?.color ?? "#64748b" },
    }))

  return {
    tooltip: {
      trigger: "item",
      backgroundColor: "#1e293b",
      borderColor: "#334155",
      textStyle: { color: "#e2e8f0", fontSize: 12 },
      formatter: (params: { seriesName: string; value: [number, number] }) => {
        return `${params.seriesName}<br>近地点: ${params.value[0].toFixed(1)} km<br>远地点: ${params.value[1].toFixed(1)} km`
      },
    },
    legend: {
      textStyle: { color: "#94a3b8", fontSize: 11 },
    },
    grid: { left: 55, right: 20, top: 40, bottom: 35 },
    xAxis: {
      type: "value",
      name: "近地点 (km)",
      nameTextStyle: { color: "#94a3b8", fontSize: 11 },
      axisLabel: { color: "#94a3b8", fontSize: 11 },
      splitLine: { lineStyle: { color: "#1e293b" } },
      axisLine: { lineStyle: { color: "#334155" } },
    },
    yAxis: {
      type: "value",
      name: "远地点 (km)",
      nameTextStyle: { color: "#94a3b8", fontSize: 11 },
      axisLabel: { color: "#94a3b8", fontSize: 11 },
      splitLine: { lineStyle: { color: "#1e293b" } },
      axisLine: { lineStyle: { color: "#334155" } },
    },
    series,
  }
})
</script>

<template>
  <VChart class="chart" :option="option" autoresize />
</template>

<style scoped>
.chart {
  width: 100%;
  height: 300px;
}
</style>
