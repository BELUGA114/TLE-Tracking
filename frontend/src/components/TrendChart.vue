<script setup lang="ts">
import { computed } from "vue"
import VChart from "vue-echarts"
import "../echarts"
import type { HistoryRecord } from "../types"

const props = defineProps<{
  records: HistoryRecord[]
}>()

const COLORS = ["#38bdf8", "#4ade80", "#f87171", "#fbbf24", "#a78bfa", "#fb923c", "#f472b6", "#22d3ee"]

interface SatGroup {
  norad: number
  name: string
  points: { epoch: number; periapsis: number; apoapsis: number; incl: number }[]
}

const groups = computed<SatGroup[]>(() => {
  const map = new Map<number, SatGroup>()
  for (const r of props.records) {
    if (r.norad == null) continue
    let g = map.get(r.norad)
    if (!g) {
      g = { norad: r.norad, name: r.name, points: [] }
      map.set(r.norad, g)
    }
    const epoch = new Date(r.epoch).getTime()
    if (isNaN(epoch) || r.periapsis == null || r.apoapsis == null) continue
    g.points.push({
      epoch,
      periapsis: r.periapsis,
      apoapsis: r.apoapsis,
      incl: r.incl ?? 0,
    })
  }
  // sort points by epoch within each group
  for (const g of map.values()) {
    g.points.sort((a, b) => a.epoch - b.epoch)
  }
  return [...map.values()].sort((a, b) => a.norad - b.norad)
})

const option = computed(() => {
  interface TrendSeriesItem {
    name: string
    type: "line"
    data: [number, number][]
    symbol: "none"
    lineStyle: { width: number; type?: string; color: string }
    itemStyle: { color: string }
  }
  const series: TrendSeriesItem[] = []
  groups.value.forEach((g, i) => {
    const color = COLORS[i % COLORS.length]
    const epochs = g.points.map((p) => p.epoch)
    series.push(
      {
        name: `${g.norad} ${g.name} 近地点`,
        type: "line",
        data: epochs.map((e, j) => [e, g.points[j].periapsis]),
        symbol: "none",
        lineStyle: { width: 1.5, color },
        itemStyle: { color },
      },
      {
        name: `${g.norad} ${g.name} 远地点`,
        type: "line",
        data: epochs.map((e, j) => [e, g.points[j].apoapsis]),
        symbol: "none",
        lineStyle: { width: 1.5, type: "dashed", color },
        itemStyle: { color },
      }
    )
  })

  return {
    tooltip: {
      trigger: "axis",
      backgroundColor: "#1e293b",
      borderColor: "#334155",
      textStyle: { color: "#e2e8f0", fontSize: 12 },
      formatter: (params: { seriesName: string; value: [number, number] }[]) => {
        if (!params.length) return ""
        const date = new Date(params[0].value[0]).toISOString().slice(0, 19)
        let html = `<div style="margin-bottom:4px">${date}</div>`
        for (const p of params) {
          html += `<div style="display:flex;justify-content:space-between;gap:1rem;">
            <span>${p.seriesName}</span>
            <span style="font-weight:600">${Number(p.value[1]).toFixed(1)} km</span>
          </div>`
        }
        return html
      },
    },
    legend: {
      type: "scroll",
      bottom: -5,
      textStyle: { color: "#94a3b8", fontSize: 11, overflow: "truncate" },
      pageTextStyle: { color: "#94a3b8" },
      pageIconColor: "#64748b",
      pageIconInactiveColor: "#334155",
    },
    grid: { left: 50, right: 20, top: 50, bottom: 45 },
    xAxis: {
      type: "time",
      axisLabel: {
        color: "#94a3b8",
        fontSize: 11,
        formatter: (val: number) => {
          const d = new Date(val)
          return `${d.getMonth() + 1}/${d.getDate()}`
        },
      },
      axisLine: { lineStyle: { color: "#334155" } },
      splitLine: { lineStyle: { color: "#1e293b" } },
    },
    yAxis: {
      type: "value",
      scale: true,
      name: "高度 (km)",
      nameTextStyle: { color: "#94a3b8", fontSize: 11 },
      axisLabel: { color: "#94a3b8", fontSize: 11 },
      splitLine: { lineStyle: { color: "#1e293b" } },
    },
    series,
    dataZoom: [
      {
        type: "inside",
        start: 0,
        end: 100,
      },
    ],
  }
})
</script>

<template>
  <div class="card chart-card">
    <h3 class="chart-title">轨道高度变化趋势</h3>
    <div v-if="groups.length" class="chart-hint">滚轮缩放 · 拖拽平移 · 图例筛选</div>
    <div v-else class="chart-empty">暂无数据</div>
    <VChart v-if="groups.length" class="chart" :option="option" autoresize />
  </div>
</template>

<style scoped>
.chart-card {
  margin-bottom: 1.5rem;
}
.chart-title {
  font-size: 0.9rem;
  color: #94a3b8;
  margin-bottom: 0.25rem;
}
.chart-hint {
  font-size: 0.75rem;
  color: #64748b;
  margin-bottom: 0.5rem;
}
.chart-empty {
  text-align: center;
  padding: 2rem;
  color: #64748b;
}
.chart {
  width: 100%;
  height: 300px;
}
</style>
