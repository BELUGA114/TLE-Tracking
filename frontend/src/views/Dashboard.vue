<template>
  <div>
    <h2 class="page-title">仪表盘</h2>

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

    <div class="card" style="padding: 0;">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:40px"></th>
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
            <template v-for="sat in satellites" :key="sat.norad">
              <tr class="record-row" @click="toggle($event)">
                <td class="arrow">▶</td>
                <td><strong>{{ sat.norad }}</strong></td>
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
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import type { Satellite } from "../types"
import { fetchSatellites } from "../api"
import DetailItem from "../components/DetailItem.vue"

const satellites = ref<Satellite[]>([])
const totalRecords = ref(0)

onMounted(async () => {
  try {
    const data = await fetchSatellites()
    satellites.value = data.satellites
    totalRecords.value = data.total
  } catch (e) {
    console.error("加载卫星数据失败", e)
  }
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
  }[type] || "tag"
}

function changeLabel(type: string) {
  return {
    initial: "初始",
    correction: "修正",
    maneuver: "机动",
  }[type] || type
}

function classificationLabel(cls: string) {
  const labels: Record<string, string> = { U: "公开", C: "保密", S: "机密" }
  return cls ? `${cls}（${labels[cls] || "未知"}）` : "-"
}
</script>
