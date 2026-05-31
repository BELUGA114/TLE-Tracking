<template>
  <div>
    <h2 class="page-title">TLE 变化历史 <span class="total-badge">{{ records.length }} 条</span></h2>

    <div class="filter-bar">
      <span class="filter-label">卫星筛选：</span>
      <label class="filter-all">
        <input type="checkbox" :checked="allChecked" @change="toggleAll">
        <span>全选</span>
      </label>
      <label v-for="sat in satelliteList" :key="sat.norad" class="filter-chip" :class="{ active: visible[sat.norad] }">
        <input type="checkbox" :checked="visible[sat.norad]" @change="toggleSat(sat.norad)">
        <span>{{ sat.norad }} {{ sat.name }}</span>
      </label>
    </div>

    <TrendChart :records="filteredRecords" />

    <div class="card" style="padding: 0;">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:40px"></th>
              <th>历元</th>
              <th>NORAD ID</th>
              <th>名称</th>
              <th>类型</th>
              <th>来源</th>
              <th>近地点 (km)</th>
              <th>远地点 (km)</th>
              <th>倾角 (°)</th>
              <th>偏心率</th>
              <th>周期 (min)</th>
              <th>Hash</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="r in filteredRecords" :key="recordId(r)">
              <tr class="record-row" @click="toggleDetail($event, recordId(r))">
                <td class="arrow">▶</td>
                <td style="white-space:nowrap;">{{ (r.epoch || "").slice(0, 19) }}</td>
                <td><strong>{{ r.norad }}</strong></td>
                <td>{{ r.name }}</td>
                <td>
                  <span :class="tagClass(r.change_type)">{{ changeLabel(r.change_type) }}</span>
                </td>
                <td>{{ r.source || "-" }}</td>
                <td>{{ r.periapsis?.toFixed(1) ?? "-" }}</td>
                <td>{{ r.apoapsis?.toFixed(1) ?? "-" }}</td>
                <td>{{ r.incl?.toFixed(2) ?? "-" }}</td>
                <td>{{ r.ecc?.toFixed(5) ?? "-" }}</td>
                <td>{{ r.period?.toFixed(3) ?? "-" }}</td>
                <td style="font-family:monospace;font-size:0.8rem;">{{ (r.tle_hash || "").slice(0, 12) }}</td>
              </tr>
              <tr class="detail-row" :style="{ display: expanded[recordId(r)] ? 'table-row' : 'none' }">
                <td colspan="12">
                  <div class="detail-grid">
                    <DetailItem label="接收时间" :value="(r.timestamp || '').slice(0, 19)" />
                    <DetailItem label="升交点赤经 (°)" :value="r.RA_OF_ASC_NODE?.toFixed(4) ?? '-'" />
                    <DetailItem label="近地点辐角 (°)" :value="r.ARG_OF_PERICENTER?.toFixed(4) ?? '-'" />
                    <DetailItem label="国际编号" :value="r.intl_id || '-'" />
                    <DetailItem label="平近点角 (°)" :value="r.MEAN_ANOMALY?.toFixed(4) ?? '-'" />
                    <DetailItem label="平运动 (圈/天)" :value="r.MEAN_MOTION?.toFixed(6) ?? '-'" />
                    <DetailItem label="B* 阻力系数" :value="r.bstar != null ? r.bstar.toExponential(4) : '-'" />
                    <DetailItem label="平运动一阶导" :value="r.MEAN_MOTION_DOT != null ? r.MEAN_MOTION_DOT.toExponential(4) : '-'" />
                    <DetailItem label="历元时圈数" :value="String(r.REV_AT_EPOCH ?? '-')" />
                    <DetailItem label="保密等级" :value="classificationLabel(r.CLASSIFICATION_TYPE)" />
                    <DetailItem label="TLE 行1" :value="r.tle1 || '-'" wide />
                    <DetailItem label="TLE 行2" :value="r.tle2 || '-'" wide />
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!records.length">
              <td colspan="12" style="text-align:center;color:#64748b;">加载中...</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue"
import type { HistoryRecord } from "../types"
import DetailItem from "../components/DetailItem.vue"
import TrendChart from "../components/TrendChart.vue"
import { useWebSocket } from "../composables/useWebSocket"

const { historyRecords: records } = useWebSocket()
const visible = ref<Record<number, boolean>>({})
const expanded = ref<Record<string, boolean>>({})

function recordId(r: HistoryRecord): string {
  return r.tle_hash || `${r.norad}-${r.epoch}`
}

const satelliteList = computed(() => {
  const map = new Map<number, { norad: number; name: string }>()
  for (const r of records.value) {
    if (r.norad != null && !map.has(r.norad)) {
      map.set(r.norad, { norad: r.norad, name: r.name })
    }
  }
  return [...map.values()].sort((a, b) => a.norad - b.norad)
})

const allChecked = computed(() =>
  satelliteList.value.every((s) => visible.value[s.norad])
)

const filteredRecords = computed(() =>
  records.value.filter((r) => visible.value[r.norad])
)

// 新数据到达时，自动将新出现的卫星标记为可见
watch(
  () => records.value.map((r) => r.norad),
  (norads) => {
    for (const id of norads) {
      if (id != null && visible.value[id] == null) {
        visible.value[id] = true
      }
    }
  },
  { immediate: true }
)

function toggleAll() {
  const next = !allChecked.value
  for (const k of Object.keys(visible.value)) {
    visible.value[Number(k)] = next
  }
}

function toggleSat(norad: number) {
  visible.value[norad] = !visible.value[norad]
}

function toggleDetail(ev: MouseEvent, id: string) {
  expanded.value[id] = !expanded.value[id]
  const row = ev.currentTarget as HTMLElement
  const arrow = row.querySelector(".arrow") as HTMLElement
  if (arrow) arrow.textContent = expanded.value[id] ? "▼" : "▶"
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
