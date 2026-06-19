<template>
  <div ref="containerRef" class="cesium-container">
    <div v-if="loading" class="cesium-overlay">🌍 加载 3D 地球…</div>
    <div v-if="error" class="cesium-overlay cesium-error">{{ error }}</div>
    <div v-if="fallback" class="cesium-overlay cesium-fallback">⚠ GPU 加速不可用，使用 CPU 传播</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue"
import type { Satellite } from "../types"
import type * as Cesium from "cesium"
import { useGpuPropagation } from "../composables/useGpuPropagation"

const props = defineProps<{
  satellites: Satellite[]
}>()

const containerRef = ref<HTMLDivElement>()
const loading = ref(true)
const error = ref("")
const fallback = ref(false)

const { state, data, registerSatellites } = useGpuPropagation()

let CesiumModule: typeof Cesium | null = null
let viewer: Cesium.Viewer | null = null
let primitivesCollection: Cesium.PointPrimitiveCollection | null = null
let orbitCollection: Cesium.PolylineCollection | null = null
let preAllocated: Cesium.Cartesian3[] = []
let prevDataCount = 0
let preRenderRemove: (() => void) | null = null
let lastOrbitCenterMs = 0

function flyHome() {
  if (!CesiumModule || !viewer) return
  viewer.camera.flyTo({
    destination: CesiumModule.Cartesian3.fromDegrees(116.4, 39.9, 25000000),
    duration: 0.5,
  })
}

function dateToJulian(d: Date): number {
  return 2440587.5 + d.getTime() / 86400000
}

// Newton-Raphson 求解开普勒方程: M = E - e·sin(E)，转为真近点角 ν
// 返回未归化的 ν（保留圈数），避免大时间跨度下 ν 被折叠到 [−π, π]
function meanAnomalyToTrueAnomaly(M_rad: number, ecc: number): number {
  const M_wrapped = ((M_rad % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)
  const rev = M_rad - M_wrapped // 整圈偏移（2π 的整数倍）
  let E = M_wrapped
  for (let i = 0; i < 20; i++) {
    const dE = (M_wrapped - E + ecc * Math.sin(E)) / (1 - ecc * Math.cos(E))
    E += dE
    if (Math.abs(dE) < 1e-14) break
  }
  const sinNu = Math.sqrt(1 - ecc * ecc) * Math.sin(E) / (1 - ecc * Math.cos(E))
  const cosNu = (Math.cos(E) - ecc) / (1 - ecc * Math.cos(E))
  return Math.atan2(sinNu, cosNu) + rev // 还原圈数
}

function computeOrbitPaths(satellites: Satellite[]) {
  if (!CesiumModule || !orbitCollection) return
  orbitCollection.removeAll()
  if (!satellites.length) return

  lastOrbitCenterMs = state.simTime.getTime()
  const simJulian = dateToJulian(state.simTime)

  for (const sat of satellites) {
    if (!sat.tle1 || !sat.tle2) continue
    try {
      const consts = data.constantsByNorad.get(sat.norad)
      if (!consts) continue

      const meanMotion = parseFloat(sat.tle2.substring(51, 63).trim())
      const periodMinutes = meanMotion > 0 ? 1440 / meanMotion : 90
      const ecc = sat.ecc || 0

      const epochDate = new Date(sat.epoch)
      if (isNaN(epochDate.getTime())) continue
      const epochJulian = dateToJulian(epochDate)
      const currentMinutesSinceEpoch = (simJulian - epochJulian) * 1440

      // 自适应采样：LEO 等时间 16 点，HEO 等真近点角 32 点（近地点加密）
      const useTrueAnomaly = ecc >= 0.2
      const numSamples = useTrueAnomaly ? 32 : 16
      const subSteps = 8

      const raw: { pos: number[]; vel: number[]; dtSec: number }[] = []

      if (useTrueAnomaly) {
        const M0_deg = parseFloat(sat.tle2.substring(43, 51).trim()) || 0
        const M0_rad = M0_deg * Math.PI / 180
        const nRadPerMin = meanMotion * 2 * Math.PI / 1440
        const M_sim = M0_rad + nRadPerMin * currentMinutesSinceEpoch
        const nu_sim = meanAnomalyToTrueAnomaly(M_sim, ecc)

        for (let j = 0; j <= numSamples; j++) {
          const nu = nu_sim + 2 * Math.PI * (j / numSamples - 0.5)
          const sinNu2 = Math.sin(nu / 2)
          const cosNu2 = Math.cos(nu / 2)
          let E = 2 * Math.atan2(
            Math.sqrt((1 - ecc) / (1 + ecc)) * sinNu2,
            cosNu2,
          )
          // atan2 折叠在 (−2π, 2π]；以 ν 为参考，用 round 确定正确圈数
          // 对于所有 e<1 的椭圆轨道 |E−ν| < π，此修正总是正确的
          E += Math.round((nu - E) / (2 * Math.PI)) * 2 * Math.PI
          const M = E - ecc * Math.sin(E)
          const minutesSinceEpoch = (M - M0_rad) / nRadPerMin
          const pred = consts.propagate(minutesSinceEpoch)
          raw.push({
            pos: [pred.position[0] * 1000, pred.position[1] * 1000, pred.position[2] * 1000],
            vel: [pred.velocity[0] * 1000, pred.velocity[1] * 1000, pred.velocity[2] * 1000],
            dtSec: minutesSinceEpoch * 60,
          })
        }
      } else {
        const halfPeriod = Math.min(periodMinutes, 1440) / 2
        for (let j = 0; j <= numSamples; j++) {
          const minutesSinceEpoch = currentMinutesSinceEpoch - halfPeriod + (j / numSamples) * periodMinutes
          const pred = consts.propagate(minutesSinceEpoch)
          raw.push({
            pos: [pred.position[0] * 1000, pred.position[1] * 1000, pred.position[2] * 1000],
            vel: [pred.velocity[0] * 1000, pred.velocity[1] * 1000, pred.velocity[2] * 1000],
            dtSec: minutesSinceEpoch * 60,
          })
        }
      }

      if (raw.length < 2) continue

      // 三次埃尔米特插值：利用 SGP4 的速度 v (m/s) 作为切线，
      // 乘以段时长 dt (s) 得到对归一化参数 t ∈ [0,1] 的导数
      // p(t) = h00·p0 + h10·(v0·dt) + h01·p1 + h11·(v1·dt)
      const posArray: number[] = []
      for (let j = 0; j < numSamples; j++) {
        const s0 = raw[j], s1 = raw[j + 1]
        const dt = s1.dtSec - s0.dtSec
        const p0 = s0.pos, v0 = s0.vel
        const p1 = s1.pos, v1 = s1.vel
        for (let k = 0; k < subSteps; k++) {
          const t = k / subSteps
          const t2 = t * t, t3 = t2 * t
          const h00 = 2*t3 - 3*t2 + 1
          const h10 = t3 - 2*t2 + t
          const h01 = -2*t3 + 3*t2
          const h11 = t3 - t2
          posArray.push(
            h00 * p0[0] + h10 * v0[0] * dt + h01 * p1[0] + h11 * v1[0] * dt,
            h00 * p0[1] + h10 * v0[1] * dt + h01 * p1[1] + h11 * v1[1] * dt,
            h00 * p0[2] + h10 * v0[2] * dt + h01 * p1[2] + h11 * v1[2] * dt,
          )
        }
      }
      const last = raw[raw.length - 1]
      posArray.push(last.pos[0], last.pos[1], last.pos[2])

      if (posArray.length < 9) continue

      const cartesians = new Array(posArray.length / 3)
      for (let j = 0; j < cartesians.length; j++) {
        cartesians[j] = new CesiumModule.Cartesian3(
          posArray[j * 3], posArray[j * 3 + 1], posArray[j * 3 + 2],
        )
      }

      const polyline = orbitCollection.add({ positions: cartesians, width: 1 })
      polyline.material = CesiumModule.Material.fromType("Color")
      polyline.material.uniforms.color = new CesiumModule.Color(0.29, 0.83, 0.50, 0.3)
    } catch (err) {
      console.warn(`[CesiumViewer] 轨道计算失败 [${sat.norad}]:`, err)
    }
  }
}

function rebuildPoints(count: number) {
  if (!CesiumModule || !primitivesCollection) return
  primitivesCollection.removeAll()
  preAllocated = []
  for (let i = 0; i < count; i++) {
    // 优先使用当前传播结果初始化位置，避免在地心闪烁一帧
    const o = i * 3
    const x = data.positions ? data.positions[o] : 0
    const y = data.positions ? data.positions[o + 1] : 0
    const z = data.positions ? data.positions[o + 2] : 0
    const pos = new CesiumModule.Cartesian3(x, y, z)
    preAllocated.push(pos)
    primitivesCollection.add({
      position: pos,
      color: CesiumModule.Color.fromCssColorString("#4ade80"),
      pixelSize: 5,
      outlineColor: CesiumModule.Color.fromCssColorString("#166534"),
      outlineWidth: 1,
    })
  }
  prevDataCount = count
}

function onPreRender() {
  if (!CesiumModule || !primitivesCollection || !data.positions) {
    return
  }

  // 卫星数量变化→重建点集
  if (data.count !== prevDataCount) {
    rebuildPoints(data.count)
    return
  }

  const simDate = state.simTime

  // 更新每颗卫星位置
  const count = Math.min(data.count, preAllocated.length, primitivesCollection.length)
  for (let i = 0; i < count; i++) {
    const o = i * 3
    const pos = preAllocated[i]
    pos.x = data.positions[o]
    pos.y = data.positions[o + 1]
    pos.z = data.positions[o + 2]
    primitivesCollection.get(i).position = pos
  }

  // 仿真时间偏离轨道中心超过 10 分钟时重算
  if (count > 0 && Math.abs(simDate.getTime() - lastOrbitCenterMs) > 600000) {
    computeOrbitPaths(props.satellites)
  }
}

onMounted(async () => {
  if (!containerRef.value) return

  try {
    CesiumModule = await import("cesium")
    await import("cesium/Build/Cesium/Widgets/widgets.css")

    viewer = new CesiumModule.Viewer(containerRef.value, {
      animation: false,
      timeline: false,
      geocoder: false,
      homeButton: true,
      sceneModePicker: false,
      baseLayerPicker: false,
      navigationHelpButton: false,
      infoBox: false,
      fullscreenButton: false,
      selectionIndicator: false,
    })

    viewer.scene.backgroundColor = CesiumModule.Color.fromCssColorString("#0b1526")
    viewer.scene.globe.baseColor = CesiumModule.Color.fromCssColorString("#1a2a40")

    // Cesium 1.141 类型声明缺少数个运行时属性
    type CameraCtl = Cesium.ScreenSpaceCameraController & {
      invertZoom: boolean
      minimumZoomRate: number
      maximumZoomRate: number
    }
    const controller = viewer.scene.screenSpaceCameraController as CameraCtl
    controller.enableCollisionDetection = true
    controller.minimumZoomDistance = 500000
    controller.maximumZoomDistance = 100000000
    controller.invertZoom = true
    controller.minimumZoomRate = 5000
    controller.maximumZoomRate = 500000

    viewer.scene.mode = CesiumModule.SceneMode.SCENE3D
    viewer.scene.morphTo3D(0)

    viewer.scene.renderError.addEventListener((_scene: Cesium.Scene, err: Error) => {
      console.warn("[Cesium] 渲染错误:", err.message)
      return true
    })

    flyHome()

    viewer.homeButton.viewModel.command.beforeExecute.addEventListener(() => {
      flyHome()
    })

    primitivesCollection = viewer.scene.primitives.add(
      new CesiumModule.PointPrimitiveCollection()
    )

    orbitCollection = viewer.scene.primitives.add(
      new CesiumModule.PolylineCollection()
    )

    // TEME 惯性系：保持 IDENTITY，让地球自然地心旋转
    if (primitivesCollection) primitivesCollection.modelMatrix = CesiumModule.Matrix4.IDENTITY
    if (orbitCollection) orbitCollection.modelMatrix = CesiumModule.Matrix4.IDENTITY

    if (props.satellites.length > 0) {
      registerSatellites(props.satellites)
      computeOrbitPaths(props.satellites)
    }

    preRenderRemove = viewer.scene.preRender.addEventListener(onPreRender)

    loading.value = false
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error("[Cesium] 启动失败:", err)
    error.value = `CesiumJS 启动失败: ${msg}`
    loading.value = false
  }
})

onUnmounted(() => {
  if (preRenderRemove) preRenderRemove()
  if (viewer) {
    viewer.destroy()
    viewer = null
  }
  CesiumModule = null
})

watch(
  () => props.satellites,
  (sats, oldSats) => {
    const old = oldSats || []
    // 未变时跳过重注册（比较 NORAD ID 和 TLE 哈希）
    if (
      old.length === sats.length &&
      old.every((o, i) => o.norad === sats[i].norad && o.tle_hash === sats[i].tle_hash)
    ) {
      return
    }
    registerSatellites(sats)
    computeOrbitPaths(sats)
  },
  { deep: false },
)

watch(
  () => state.isFallback,
  (v) => { fallback.value = v },
)

watch(
  () => state.error,
  (msg) => {
    if (msg) error.value = msg
  },
)
</script>

<style scoped>
.cesium-container {
  position: relative;
  width: 100%;
  height: calc(100vh - 160px);
  min-height: 500px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #334155;
}
.cesium-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 1.1rem;
  z-index: 10;
  pointer-events: none;
}
.cesium-error {
  color: #f87171;
}
.cesium-fallback {
  color: #fbbf24;
  font-size: 0.85rem;
  top: auto;
  bottom: 12px;
  height: auto;
  padding: 0.25rem 0;
}
</style>
