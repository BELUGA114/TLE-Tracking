<script setup lang="ts">
import { computed } from "vue"
import VChart from "vue-echarts"
import "../echarts"
import type { Satellite } from "../types"

const props = defineProps<{
  satellites: Satellite[]
}>()

const bins = [
  { label: "0-200", min: 0, max: 200 },
  { label: "200-400", min: 200, max: 400 },
  { label: "400-600", min: 400, max: 600 },
  { label: "600-800", min: 600, max: 800 },
  { label: "800-1000", min: 800, max: 1000 },
  { label: "1000-1500", min: 1000, max: 1500 },
  { label: "≥1500", min: 1500, max: Infinity },
]

const option = computed(() => {
  const valid = props.satellites.filter((s) => s.periapsis != null)
  const counts = bins.map((b) =>
    valid.filter((s) => s.periapsis >= b.min && s.periapsis < b.max).length
  )
  const missing = props.satellites.length - valid.length

  return {
    title: missing > 0 ? {
      text: `${valid.length} 颗`,
      subtext: `${missing} 颗无轨道数据`,
      left: "right",
      top: 0,
      textStyle: { color: "#64748b", fontSize: 11, fontWeight: 400 },
      subtextStyle: { color: "#64748b", fontSize: 10 },
    } : undefined,
    tooltip: {
      trigger: "axis",
      backgroundColor: "#1e293b",
      borderColor: "#334155",
      textStyle: { color: "#e2e8f0", fontSize: 12 },
    },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: "category",
      data: bins.map((b) => b.label),
      axisLabel: { color: "#94a3b8", fontSize: 11 },
      axisLine: { lineStyle: { color: "#334155" } },
      axisTick: { lineStyle: { color: "#334155" } },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: { color: "#94a3b8", fontSize: 11 },
      splitLine: { lineStyle: { color: "#1e293b" } },
    },
    series: [
      {
        type: "bar",
        data: counts,
        itemStyle: {
          color: {
            type: "linear",
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "#38bdf8" },
              { offset: 1, color: "#0284c7" },
            ],
          },
          borderRadius: [4, 4, 0, 0],
        },
        emphasis: {
          itemStyle: { color: "#7dd3fc" },
        },
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
