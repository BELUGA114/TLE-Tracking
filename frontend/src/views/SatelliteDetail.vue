<template>
  <div>
    <router-link to="/" class="back-link">
      <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5">
        <polyline points="8.5,2.5 4,7 8.5,11.5" />
      </svg>
      返回仪表盘
    </router-link>

    <div v-if="sat">
      <h2 class="page-title">{{ sat.name }} <span class="total-badge">#{{ sat.norad }}</span></h2>

      <div class="cards cards-2">
        <div class="card">
          <h3>最后变化</h3>
          <div class="value"><span :class="tagClass(sat.change_type)">{{ changeLabel(sat.change_type) }}</span></div>
          <div class="sub">来源: {{ sat.source || "-" }}</div>
        </div>
        <div class="card">
          <h3>历元</h3>
          <div class="value" style="font-size:1.2rem;">{{ (sat.epoch || "").slice(0, 19) }}</div>
          <div class="sub">国际编号: {{ sat.intl_id || "-" }}</div>
        </div>
      </div>

      <div class="card" style="margin-bottom:1.5rem;">
        <h3 class="section-title">最新轨道参数</h3>
        <div class="detail-grid">
          <DetailItem label="近地点 (km)" :value="sat.periapsis?.toFixed(1) ?? '-'" />
          <DetailItem label="远地点 (km)" :value="sat.apoapsis?.toFixed(1) ?? '-'" />
          <DetailItem label="倾角 (°)" :value="sat.incl?.toFixed(2) ?? '-'" />
          <DetailItem label="偏心率" :value="sat.ecc?.toFixed(5) ?? '-'" />
          <DetailItem label="周期 (min)" :value="sat.period?.toFixed(3) ?? '-'" />
          <DetailItem label="B* 阻力系数" :value="sat.bstar != null ? sat.bstar.toExponential(4) : '-'" />
          <DetailItem label="升交点赤经 (°)" :value="sat.RA_OF_ASC_NODE?.toFixed(4) ?? '-'" />
          <DetailItem label="近地点辐角 (°)" :value="sat.ARG_OF_PERICENTER?.toFixed(4) ?? '-'" />
          <DetailItem label="平近点角 (°)" :value="sat.MEAN_ANOMALY?.toFixed(4) ?? '-'" />
          <DetailItem label="平运动 (圈/天)" :value="sat.MEAN_MOTION?.toFixed(6) ?? '-'" />
          <DetailItem label="平运动一阶导" :value="sat.MEAN_MOTION_DOT != null ? sat.MEAN_MOTION_DOT.toExponential(4) : '-'" />
          <DetailItem label="保密等级" :value="classificationLabel(sat.CLASSIFICATION_TYPE)" />
          <DetailItem label="历元时圈数" :value="String(sat.REV_AT_EPOCH ?? '-')" />
          <DetailItem label="根数集编号" :value="String(sat.ELEMENT_SET_NO ?? '-')" />
        </div>
      </div>

      <TrendChart :records="satelliteHistory" />

      <div class="card" style="padding: 0; margin-top: 1.5rem;">
        <h3 class="section-title" style="padding:0.75rem 1rem;margin:0;">最近变化</h3>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>历元</th>
                <th>类型</th>
                <th>近地点 (km)</th>
                <th>远地点 (km)</th>
                <th>倾角 (°)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in satelliteHistory" :key="r.tle_hash">
                <td style="white-space:nowrap;">{{ (r.epoch || "").slice(0, 19) }}</td>
                <td><span :class="tagClass(r.change_type)">{{ changeLabel(r.change_type) }}</span></td>
                <td>{{ r.periapsis?.toFixed(1) ?? "-" }}</td>
                <td>{{ r.apoapsis?.toFixed(1) ?? "-" }}</td>
                <td>{{ r.incl?.toFixed(2) ?? "-" }}</td>
              </tr>
              <tr v-if="!satelliteHistory.length">
                <td colspan="5" style="text-align:center;color:#64748b;">暂无历史数据</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div v-else>
      <template v-if="loading">
        <div class="skeleton skeleton-card" style="margin-bottom:1rem;"></div>
        <div class="skeleton skeleton-card" style="height:200px;"></div>
      </template>
      <div v-else class="empty-card">
        <p>未找到该卫星</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { useRoute } from "vue-router"
import DetailItem from "../components/DetailItem.vue"
import TrendChart from "../components/TrendChart.vue"
import { useWebSocket } from "../composables/useWebSocket"
import { fetchSatelliteHistory } from "../api"
import type { HistoryRecord } from "../types"

const route = useRoute()
const noradId = Number(route.params.noradId)

const { satellites, historyRecords, loading } = useWebSocket()

const sat = computed(() => satellites.value.find((s) => s.norad === noradId))

// 优先通过 REST API 获取该卫星的完整变化历史，避免 WebSocket 仅推送全局最近 100 条的问题
const satelliteHistory = ref<HistoryRecord[]>([])

onMounted(async () => {
  try {
    const res = await fetchSatelliteHistory(noradId, 200)
    satelliteHistory.value = res.records
  } catch {
    // REST API 不可用时回退到 WebSocket 全局历史
    satelliteHistory.value = historyRecords.value.filter((r) => r.norad === noradId)
  }
})

function tagClass(type: string) {
  return {
    initial: "tag tag-initial",
    correction: "tag tag-correction",
    maneuver: "tag tag-maneuver",
    decaying: "tag tag-decaying",
  }[type] || "tag"
}

function changeLabel(type: string) {
  return {
    initial: "初始",
    correction: "修正",
    maneuver: "机动",
    decaying: "衰降",
  }[type] || type
}

function classificationLabel(cls: string) {
  const labels: Record<string, string> = { U: "公开", C: "保密", S: "机密" }
  return cls ? `${cls}（${labels[cls] || "未知"}）` : "-"
}
</script>

<style scoped>
.section-title {
  font-family: var(--font-heading);
  font-size: 0.9rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--color-signal-gold);
  margin-bottom: 0.75rem;
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 0.75rem;
}
</style>
