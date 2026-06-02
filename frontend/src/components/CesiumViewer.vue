<template>
  <div ref="containerRef" class="cesium-container">
    <div v-if="loading" class="cesium-overlay">🌍 加载 3D 地球…</div>
    <div v-if="error" class="cesium-overlay cesium-error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue"
import type { Satellite } from "../types"
import { computeSatellitePosition } from "../utils/orbit"

const props = defineProps<{
  satellites: Satellite[]
}>()

const containerRef = ref<HTMLDivElement>()
const loading = ref(true)
const error = ref("")

let CesiumModule: any = null
let viewer: any = null
let primitivesCollection: any = null
let animFrameId = 0

/** 飞到安全视角 */
function flyHome() {
  if (!CesiumModule || !viewer) return
  viewer.camera.flyTo({
    destination: CesiumModule.Cartesian3.fromDegrees(116.4, 39.9, 25000000),
    duration: 0.5,
  })
}

function animate(sats: Satellite[]) {
  if (!CesiumModule || !primitivesCollection) return
  const now = new Date()

  for (let i = 0; i < primitivesCollection.length; i++) {
    const p = primitivesCollection.get(i)
    if (!p) continue
    const sat = sats[i]
    if (!sat) continue
    try {
      const pos = computeSatellitePosition(sat, now)
      if (pos) {
        p.position = new CesiumModule.Cartesian3(pos.x, pos.y, pos.z)
      }
    } catch {
      // 单颗卫星的计算失败不影响其他卫星
    }
  }

  animFrameId = requestAnimationFrame(() => animate(sats))
}

function rebuildPoints(sats: Satellite[]) {
  if (!CesiumModule || !viewer || !primitivesCollection) return

  primitivesCollection.removeAll()
  const now = new Date()

  for (const sat of sats) {
    try {
      const pos = computeSatellitePosition(sat, now)
      if (!pos) continue
      primitivesCollection.add({
        position: new CesiumModule.Cartesian3(pos.x, pos.y, pos.z),
        color: CesiumModule.Color.fromCssColorString("#38bdf8"),
        pixelSize: 5,
        outlineColor: CesiumModule.Color.fromCssColorString("#0f172a"),
        outlineWidth: 1,
      })
    } catch {
      // 跳过无效卫星
    }
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

    // 暗色主题
    viewer.scene.backgroundColor = CesiumModule.Color.fromCssColorString("#0b1526")
    viewer.scene.globe.baseColor = CesiumModule.Color.fromCssColorString("#1a2a40")

    // 摄像机约束
    const controller = viewer.scene.screenSpaceCameraController
    // 阻止摄像机越过地心（防止归一化崩溃）
    controller.enableCollisionDetection = true
    controller.minimumZoomDistance = 500000
    controller.maximumZoomDistance = 100000000
    controller.invertZoom = true
    controller.minimumZoomRate = 5000
    controller.maximumZoomRate = 500000

    // 锁定摄像机到地心轨道模式，不可自由飞行到奇怪的方向
    viewer.scene.mode = CesiumModule.SceneMode.SCENE3D
    viewer.scene.morphTo3D(0)

    // 渲染错误自动恢复
    viewer.scene.renderError.addEventListener((_scene: any, err: Error) => {
      console.warn("[Cesium] 渲染错误，自动恢复:", err.message)
      // 清除错误状态，让 Cesium 继续渲染
      return true
    })

    // 初始化位置
    flyHome()

    // homeButton 自定义
    viewer.homeButton.viewModel.command.beforeExecute.addEventListener(() => {
      flyHome()
    })

    primitivesCollection = viewer.scene.primitives.add(
      new CesiumModule.PointPrimitiveCollection()
    )

    rebuildPoints(props.satellites)
    animFrameId = requestAnimationFrame(() => animate(props.satellites))
    loading.value = false
  } catch (err: any) {
    console.error("[Cesium] 启动失败:", err)
    error.value = `CesiumJS 启动失败: ${err.message || err}`
    loading.value = false
  }
})

onUnmounted(() => {
  cancelAnimationFrame(animFrameId)
  if (viewer) {
    viewer.destroy()
    viewer = null
  }
  CesiumModule = null
})

watch(
  () => props.satellites.length,
  () => { rebuildPoints(props.satellites) },
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
</style>
