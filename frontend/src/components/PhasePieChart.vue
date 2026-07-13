<script setup lang="ts">
import { computed } from "vue"
import VChart from "vue-echarts"
import "../echarts"
import { CHART_COLORS } from "../echarts"
import type { DecaySatellite } from "../types"

const props = defineProps<{
  satellites: DecaySatellite[]
}>()

const PHASES: Record<string, { label: string; color: string }> = {
  normal: { label: "正常", color: CHART_COLORS.decayPhases.normal },
  early_decay: { label: "早期衰降", color: CHART_COLORS.decayPhases.early_decay },
  accelerating: { label: "加速衰降", color: CHART_COLORS.decayPhases.accelerating },
  critical: { label: "临界", color: CHART_COLORS.decayPhases.critical },
}

const option = computed(() => {
  const counts: Record<string, number> = {}
  for (const s of props.satellites) {
    counts[s.phase] = (counts[s.phase] || 0) + 1
  }

  const data = Object.entries(counts).map(([phase, count]) => ({
    value: count,
    name: PHASES[phase]?.label ?? phase,
    itemStyle: { color: PHASES[phase]?.color ?? CHART_COLORS.axisLabel },
  }))

  return {
    tooltip: {
      trigger: "item",
      backgroundColor: CHART_COLORS.tooltipBg,
      borderColor: CHART_COLORS.tooltipBorder,
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
          color: CHART_COLORS.axisLabel,
          fontSize: 12,
        },
        labelLine: {
          lineStyle: { color: CHART_COLORS.axisLine },
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
