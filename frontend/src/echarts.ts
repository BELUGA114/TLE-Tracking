import { use } from "echarts/core"
import { BarChart, LineChart, PieChart, ScatterChart } from "echarts/charts"
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
} from "echarts/components"
import { CanvasRenderer } from "echarts/renderers"

use([
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  CanvasRenderer,
])

/*
 * 图表颜色常量——与 tokens.css 中的设计令牌保持手动同步。
 * ECharts 渲染到 Canvas 无法读取 CSS 变量，因此需在此维护副本。
 * 同步关系：
 *   series[0] = --color-signal-gold    series[1] = --color-signal-cyan
 *   series[2] = --color-nominal-green  series[3] = --color-data-blue
 *   tooltipBg  = --color-surface-raised
 *   tooltipBorder = --color-border
 *   gridLine   ≈ rgba(30,48,80,0.5)   (--color-border 半透明)
 *   axisLabel  = --color-text-muted
 *   axisLine   = --color-border
 */
export const CHART_COLORS = {
  series: ["#f59e0b", "#22d3ee", "#4ade80", "#60a5fa",
           "#fb923c", "#a78bfa", "#ef4444", "#fbbf24"],
  tooltipBg: "#182540",
  tooltipBorder: "#1e3050",
  gridLine: "rgba(30,48,80,0.5)",
  axisLabel: "#64748b",
  axisLine: "#1e3050",
  // 衰降阶段专用颜色
  decayPhases: {
    normal:       "#4ade80",
    early_decay:  "#f59e0b",
    accelerating: "#fb923c",
    critical:     "#ef4444",
  },
}
