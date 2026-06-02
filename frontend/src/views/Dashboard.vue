<template>
  <div>
    <div class="dashboard-header">
      <h2 class="page-title">仪表盘</h2>
      <button class="view-toggle" @click="toggleView">
        {{ is3d ? "☰ 2D 列表" : "🌍 3D 地球" }}
      </button>
    </div>

    <template v-if="is3d">
      <CesiumViewer :satellites="satellites" />
    </template>

    <template v-else>
      <div class="cards cards-2">
        <div class="card">
          <h3>监控目标</h3>
          <div class="value">{{ satellites.length }}</div>
          <div class="sub">颗卫星</div>
        </div>
        <div class="card">
          <h3>已有数据</h3>
          <div class="value">{{ totalRecords }}</div>
          <div class="sub">条 TLE 记录</div>
        </div>
      </div>

      <div class="card chart-card">
        <h3 class="chart-title">轨道高度分布</h3>
        <AltitudeChart :satellites="satellites" />
      </div>

      <div class="filter-bar">
        <span class="filter-label">搜索：</span>
        <input v-model="searchQuery" type="text" class="search-input" placeholder="NORAD ID 或名称..." />
        <span class="total-badge">{{ filteredSatellites.length }} / {{ satellites.length }}</span>
      </div>

      <div class="card" style="padding: 0;">
        <div class="table-wrap">
          <table style="table-layout:fixed">
            <colgroup>
              <col style="width:40px" />
              <col style="width:12%" />
              <col style="width:13%" />
              <col style="width:12%" />
              <col style="width:12%" />
              <col style="width:8%" />
              <col style="width:10%" />
              <col style="width:10%" />
              <col style="width:auto" />
            </colgroup>
            <thead>
              <tr>
                <th></th>
                <th>NORAD ID</th>
                <th>名称</th>
                <th>近地点 (km)</th>
                <th>远地点 (km)</th>
                <th>倾角 (°)</th>
                <th>偏心率</th>
                <th>周期 (min)</th>
                <th>最后变化</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="sat in filteredSatellites" :key="sat.norad">
                <tr class="record-row" @click="toggle($event)">
                  <td class="arrow">▶</td>
                  <td><router-link :to="`/satellite/${sat.norad}`" class="norad-link"><strong>{{ sat.norad }}</strong></router-link></td>
                  <td>{{ sat.name }}</td>
                  <td>{{ sat.periapsis.toFixed(1) }}</td>
                  <td>{{ sat.apoapsis.toFixed(1) }}</td>
                  <td>{{ sat.incl.toFixed(2) }}</td>
                  <td>{{ sat.ecc.toFixed(5) }}</td>
                  <td>{{ sat.period.toFixed(3) }}</td>
                  <td><span :class="tagClass(sat.change_type)">{{ changeLabel(sat.change_type) }}</span></td>
                </tr>
                <tr class="detail-row" style="display:none;">
                  <td colspan="9">
                    <div class="detail-grid">
                      <DetailItem label="升交点赤经 (°)" :value="sat.RA_OF_ASC_NODE?.toFixed(4)" />
                      <DetailItem label="近地点辐角 (°)" :value="sat.ARG_OF_PERICENTER?.toFixed(4)" />
                      <DetailItem label="平近点角 (°)" :value="sat.MEAN_ANOMALY?.toFixed(4)" />
                      <DetailItem label="平运动 (圈/天)" :value="sat.MEAN_MOTION?.toFixed(6)" />
                      <DetailItem label="平运动一阶导" :value="sat.MEAN_MOTION_DOT != null ? sat.MEAN_MOTION_DOT.toExponential(4) : '-'" />
                      <DetailItem label="B* 阻力系数" :value="sat.bstar != null ? sat.bstar.toExponential(4) : '-'" />
                      <DetailItem label="历元时圈数" :value="String(sat.REV_AT_EPOCH ?? '-')" />
                      <DetailItem label="国际编号" :value="sat.intl_id || '-'" />
                      <DetailItem label="根数集编号" :value="String(sat.ELEMENT_SET_NO ?? '-')" />
                      <DetailItem label="保密等级" :value="classificationLabel(sat.CLASSIFICATION_TYPE)" />
                      <DetailItem label="历元" :value="(sat.epoch || '').slice(0, 19)" />
                      <DetailItem label="数据来源" :value="sat.source || '-'" />
                    </div>
                  </td>
                </tr>
              </template>
              <tr v-if="!satellites.length">
                <td colspan="9" style="text-align:center;color:#64748b;">加载中...</td>
              </tr>
              <tr v-else-if="!filteredSatellites.length">
                <td colspan="9" style="text-align:center;color:#64748b;">无匹配卫星</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent } from "vue"
import DetailItem from "../components/DetailItem.vue"
import AltitudeChart from "../components/AltitudeChart.vue"
import { useWebSocket } from "../composables/useWebSocket"

const CesiumViewer = defineAsyncComponent(() => import("../components/CesiumViewer.vue"))

const { satellites, historyRecords } = useWebSocket()
const totalRecords = computed(() => historyRecords.value.length)

const is3d = ref(false)
function toggleView() {
  is3d.value = !is3d.value
}

const searchQuery = ref("")
const filteredSatellites = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return satellites.value
  return satellites.value.filter(
    (s) => String(s.norad).includes(q) || s.name.toLowerCase().includes(q)
  )
})

function toggle(ev: MouseEvent) {
  const row = (ev.currentTarget as HTMLElement)
  const detail = row.nextElementSibling as HTMLElement | null
  if (!detail || !detail.classList.contains("detail-row")) return
  const hidden = detail.style.display === "none" || !detail.style.display
  detail.style.display = hidden ? "table-row" : "none"
  const arrow = row.querySelector(".arrow") as HTMLElement
  if (arrow) arrow.textContent = hidden ? "▼" : "▶"
}

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
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}
.dashboard-header .page-title {
  margin-bottom: 0;
}
.view-toggle {
  background: #0ea5e9;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 0.45rem 1rem;
  font-size: 0.85rem;
  cursor: pointer;
  transition: background 0.15s;
}
.view-toggle:hover {
  background: #0284c7;
}
.chart-card {
  margin-bottom: 1.5rem;
}
.chart-title {
  font-size: 0.9rem;
  color: #94a3b8;
  margin-bottom: 0.5rem;
}
.search-input {
  flex: 1;
  max-width: 300px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 0.35rem 0.6rem;
  color: #e2e8f0;
  font-size: 0.85rem;
  outline: none;
  transition: border-color 0.15s;
}
.search-input:focus {
  border-color: #0ea5e9;
}
.search-input::placeholder {
  color: #475569;
}
.norad-link {
  color: #38bdf8;
  text-decoration: none;
}
.norad-link:hover {
  text-decoration: underline;
}
</style>
