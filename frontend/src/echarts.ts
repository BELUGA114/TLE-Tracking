import { use } from "echarts/core"
import { BarChart, LineChart, PieChart, ScatterChart } from "echarts/charts"
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
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
  CanvasRenderer,
])
