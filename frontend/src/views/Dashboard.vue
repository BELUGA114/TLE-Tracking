<template>
  <div>
    <div class="dashboard-header">
      <h2 class="page-title">仪表盘</h2>
      <button class="btn-ghost" @click="toggleView">
        <svg v-if="is3d" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15">
          <rect x="1.5" y="1.5" width="5" height="5" rx="1" />
          <rect x="9.5" y="1.5" width="5" height="5" rx="1" />
          <rect x="1.5" y="9.5" width="5" height="5" rx="1" />
          <rect x="9.5" y="9.5" width="5" height="5" rx="1" />
        </svg>
        <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15">
          <circle cx="8" cy="8" r="6.5" />
          <ellipse cx="8" cy="8" rx="3" ry="6.5" />
          <line x1="1.5" y1="8" x2="14.5" y2="8" />
        </svg>
        {{ is3d ? "2D 列表" : "3D 地球" }}
      </button>
    </div>

    <template v-if="is3d">
      <div class="cesium-wrapper">
        <CesiumViewer :satellites="satellites" />
        <VcrControls
          :sim-time="propState.simTime"
          :is-paused="propState.isPaused"
          :prop-rate="propState.propRate"
          :is-ready="propState.isReady"
          :is-fallback="propState.isFallback"
          @update:prop-rate="setPropRate"
          @toggle-pause="togglePause"
          @reset="resetTime"
          @seek="setTimeOffset"
        />
      </div>
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
              <template v-if="!satellites.length">
                <tr v-for="i in 5" :key="'skel-'+i">
                  <td colspan="9" style="padding:0.35rem 0.75rem;">
                    <div class="skeleton skeleton-row"></div>
                  </td>
                </tr>
              </template>
              <tr v-else-if="!filteredSatellites.length">
                <td colspan="9" style="text-align:center;color:var(--color-text-muted);padding:2rem;">无匹配卫星</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, defineAsyncComponent } from "vue"
import DetailItem from "../components/DetailItem.vue"
import AltitudeChart from "../components/AltitudeChart.vue"
import VcrControls from "../components/VcrControls.vue"
import { useWebSocket } from "../composables/useWebSocket"
import { useGpuPropagation } from "../composables/useGpuPropagation"

const CesiumViewer = defineAsyncComponent(() => import("../components/CesiumViewer.vue"))

const { satellites, historyRecords } = useWebSocket()
const {
  state: propState,
  setPropRate,
  togglePause,
  resetTime,
  setTimeOffset,
} = useGpuPropagation()
const totalRecords = computed(() => historyRecords.value.length)

const is3d = ref(false)
const wasAutoPaused = ref(false)

function toggleView() {
  is3d.value = !is3d.value
}

// 2D 列表模式下暂停 GPU 传播节省资源
watch(is3d, (v) => {
  if (!v && !propState.isPaused) {
    togglePause()
    wasAutoPaused.value = true
  } else if (v && wasAutoPaused.value && propState.isPaused) {
    togglePause()
    wasAutoPaused.value = false
  }
})

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
  margin-bottom: var(--space-xl);
}
.dashboard-header .page-title {
  margin-bottom: 0;
}

.norad-link {
  color: var(--color-data-blue);
  text-decoration: none;
  font-family: var(--font-mono);
}
.norad-link:hover {
  color: var(--color-signal-gold);
  text-decoration: underline;
}

.cesium-wrapper {
  position: relative;
}

.chart-card {
  margin-bottom: var(--space-xl);
}
</style>
