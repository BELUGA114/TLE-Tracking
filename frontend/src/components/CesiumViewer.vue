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
import { useGpuPropagation } from "../composables/useGpuPropagation"
import { WasmElements, WasmConstants } from "sgp4.gl"

const props = defineProps<{
  satellites: Satellite[]
}>()

const containerRef = ref<HTMLDivElement>()
const loading = ref(true)
const error = ref("")
const fallback = ref(false)

const { state, data, registerSatellites } = useGpuPropagation()

let CesiumModule: any = null
let viewer: any = null
let primitivesCollection: any = null
let orbitCollection: any = null
let preAllocated: any[] = []
let prevDataCount = 0
let preRenderRemove: (() => void) | null = null
let frameCount = 0

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

function computeOrbitPaths(satellites: Satellite[]) {
  if (!CesiumModule || !orbitCollection) return
  orbitCollection.removeAll()
  if (!satellites.length) return

  const simJulian = dateToJulian(state.simTime)

  for (const sat of satellites) {
    if (!sat.tle1 || !sat.tle2) continue
    try {
      const el = WasmElements.from_tle(
        new TextEncoder().encode(sat.name),
        new TextEncoder().encode(sat.tle1),
        new TextEncoder().encode(sat.tle2),
      )
      const consts = WasmConstants.from_elements(el)

      // TLE line 2, columns 52-63 (0-indexed 51-62): 平均运动 (rev/day)
      const meanMotion = parseFloat(sat.tle2.substring(51, 63).trim())
      const periodMinutes = meanMotion > 0 ? 1440 / meanMotion : 90

      const steps = 512
      const epochDate = new Date(sat.epoch)
      if (isNaN(epochDate.getTime())) continue
      const epochJulian = dateToJulian(epochDate)
      // 当前仿真时刻距历元的分针数
      const currentMinutesSinceEpoch = (simJulian - epochJulian) * 1440

      const posArray: number[] = []
      const halfPeriod = periodMinutes / 2
      for (let j = 0; j <= steps; j++) {
        // 以当前时刻为中心，向前后各推半个周期
        const minutesSinceEpoch = currentMinutesSinceEpoch - halfPeriod + (j / steps) * periodMinutes
        try {
          const pred = consts.propagate(minutesSinceEpoch)
          posArray.push(
            pred.position[0] * 1000,
            pred.position[1] * 1000,
            pred.position[2] * 1000,
          )
        } catch {
          // 单个点传播失败则跳过
        }
      }

      if (posArray.length < 9) continue // 至少 3 个点

      const cartesians = new Array(posArray.length / 3)
      for (let j = 0; j < posArray.length / 3; j++) {
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
    const pos = new CesiumModule.Cartesian3(0, 0, 0)
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
  const julian = CesiumModule.JulianDate.fromDate(simDate)

  // 保持 TEME 惯性系，让 Cesium 的地球自然地心旋转
  // modelMatrix 重置为恒等矩阵，不做 TEME→Pseudo-Fixed 变换
  primitivesCollection.modelMatrix = CesiumModule.Matrix4.IDENTITY
  orbitCollection.modelMatrix = CesiumModule.Matrix4.IDENTITY

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

  // 轨道线随仿真推进漂移，每 300 帧重算对齐
  if (count > 0 && frameCount % 300 === 299) {
    computeOrbitPaths(props.satellites)
  }

  frameCount++
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

    const controller = viewer.scene.screenSpaceCameraController
    controller.enableCollisionDetection = true
    controller.minimumZoomDistance = 500000
    controller.maximumZoomDistance = 100000000
    controller.invertZoom = true
    controller.minimumZoomRate = 5000
    controller.maximumZoomRate = 500000

    viewer.scene.mode = CesiumModule.SceneMode.SCENE3D
    viewer.scene.morphTo3D(0)

    viewer.scene.renderError.addEventListener((_scene: any, err: Error) => {
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

    if (props.satellites.length > 0) {
      registerSatellites(props.satellites)
      computeOrbitPaths(props.satellites)
    }

    preRenderRemove = viewer.scene.preRender.addEventListener(onPreRender)

    loading.value = false
  } catch (err: any) {
    console.error("[Cesium] 启动失败:", err)
    error.value = `CesiumJS 启动失败: ${err.message || err}`
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
  (sats) => {
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
