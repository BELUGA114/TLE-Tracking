<script setup lang="ts">
import { computed } from "vue"
import VChart from "vue-echarts"
import "../echarts"
import { CHART_COLORS } from "../echarts"
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
      textStyle: { color: CHART_COLORS.axisLabel, fontSize: 11, fontWeight: 400 },
      subtextStyle: { color: CHART_COLORS.axisLabel, fontSize: 10 },
    } : undefined,
    tooltip: {
      trigger: "axis",
      backgroundColor: CHART_COLORS.tooltipBg,
      borderColor: CHART_COLORS.tooltipBorder,
      textStyle: { color: "#e2e8f0", fontSize: 12 },
    },
    grid: { left: 50, right: 20, top: 40, bottom: 30 },
    xAxis: {
      type: "category",
      data: bins.map((b) => b.label),
      axisLabel: { color: CHART_COLORS.axisLabel, fontSize: 11 },
      axisLine: { lineStyle: { color: CHART_COLORS.axisLine } },
      axisTick: { lineStyle: { color: CHART_COLORS.axisLine } },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: { color: CHART_COLORS.axisLabel, fontSize: 11 },
      splitLine: { lineStyle: { color: CHART_COLORS.gridLine } },
    },
    series: [
      {
        type: "bar",
        data: counts,
        itemStyle: {
          color: CHART_COLORS.series[1],
          borderRadius: [4, 4, 0, 0],
        },
        emphasis: {
          itemStyle: { color: CHART_COLORS.series[1] },
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
