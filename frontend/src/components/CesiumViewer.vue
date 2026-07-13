<template>
  <div ref="containerRef" class="cesium-container">
    <div v-if="statusMessage" class="cesium-overlay" :class="statusClass">
      {{ statusMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue"
import type { Satellite } from "../types"
import { useGpuPropagation } from "../composables/useGpuPropagation"
import { bootstrapCesium, type BootResult, isBootError } from "../cesium/CesiumBootstrapper"
import { SatelliteSceneManager } from "../cesium/SatelliteSceneManager"

const props = defineProps<{
  satellites: Satellite[]
}>()

const containerRef = ref<HTMLDivElement>()
const statusMessage = ref("")
const statusClass = ref("")

const { state, data, registerSatellites } = useGpuPropagation()

let boot: BootResult | null = null
let sceneMgr: SatelliteSceneManager | null = null
let preRenderRemove: (() => void) | null = null

/** 全量重建场景（wipe + rebuild）。卫星列表变化或 WASM 就绪时调用。 */
function rebuildScene() {
  if (!sceneMgr || data.constantsByNorad.size === 0) return
  sceneMgr.rebuild(props.satellites, data.constantsByNorad, state.simTime)
}

// 初始化
onMounted(async () => {
  if (!containerRef.value) return

  statusMessage.value = "Loading 3D Earth..."

  const result = await bootstrapCesium(containerRef.value)
  if (isBootError(result)) {
    statusMessage.value = result.error
    statusClass.value = "cesium-error"
    console.error("[CesiumViewer] Bootstrap failed:", result.error)
    return
  }

  boot = result
  sceneMgr = new SatelliteSceneManager(boot.viewer.scene, boot.Cesium)

  // 注册卫星到传播引擎
  await registerSatellites(props.satellites)

  // 首次重建（若 WASM 未就绪则 constants 为空，rebuild 跳过；
  // state.isReady watch 会在 WASM 就绪后补调）
  rebuildScene()

  // 每帧只做两件事：更新点位置 + 刷新过期轨道线
  preRenderRemove = boot.viewer.scene.preRender.addEventListener(() => {
    if (!sceneMgr) return
    if (data.positions) {
      sceneMgr.updatePoints(data.positions, data.count)
    }
    sceneMgr.refreshStaleOrbits(props.satellites, data.constantsByNorad, state.simTime)
  })

  statusMessage.value = ""
})

onUnmounted(() => {
  if (preRenderRemove) { preRenderRemove(); preRenderRemove = null }
  sceneMgr?.dispose()
  sceneMgr = null
  boot?.viewer?.destroy()
  boot = null
})

// 卫星列表变化 → 重注册 + 全量重建
watch(
  () => props.satellites,
  async (sats, oldSats) => {
    const old = oldSats || []
    if (
      old.length === sats.length &&
      old.every((o, i) => o.norad === sats[i].norad && o.tle_hash === sats[i].tle_hash)
    ) {
      return
    }
    await registerSatellites(sats)
    rebuildScene()
  },
  { deep: false },
)

// WASM 延迟就绪：propagation 引擎完成后补建 scene
watch(
  () => state.isReady,
  (ready) => {
    if (ready) rebuildScene()
  },
)

// 错误状态
watch(
  () => state.error,
  (msg) => {
    if (msg) { statusMessage.value = msg; statusClass.value = "cesium-error" }
  },
)

// GPU 回退提示
watch(
  () => state.isFallback,
  (v) => {
    if (v && !state.error) {
      statusMessage.value = "GPU acceleration unavailable, using CPU propagation"
      statusClass.value = "cesium-fallback"
    } else if (!v && statusClass.value === "cesium-fallback") {
      statusMessage.value = ""
      statusClass.value = ""
    }
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
  background: rgba(11, 21, 38, 0.85);
}
.cesium-error {
  color: #f87171;
  background: rgba(15, 23, 42, 0.92);
}
.cesium-fallback {
  color: #fbbf24;
  font-size: 0.85rem;
  top: auto;
  bottom: 12px;
  height: auto;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  background: rgba(30, 41, 59, 0.9);
}
</style>
