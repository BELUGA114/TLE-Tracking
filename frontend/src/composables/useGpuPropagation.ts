import { reactive, onMounted, onUnmounted } from "vue"
import type { Satellite } from "../types"
import wasmInit, {
  WasmElements,
  WasmConstants,
  WasmGpuConsts,
  GpuPropagator,
} from "sgp4.gl"
import wasmUrl from "sgp4.gl/wasm?url"

interface GpuPropState {
  isReady: boolean
  isFallback: boolean
  isPaused: boolean
  propRate: number
  satelliteCount: number
  simTime: Date
  error: string
}

/** 非响应式数据区域，供渲染循环每帧直接读取 */
export interface PropagationData {
  positions: Float32Array | null
  velocities: Float32Array | null
  constantsByNorad: Map<number, any>  // norad → WasmConstants，供轨道计算复用
  count: number
}

// 模块级单例
const state = reactive<GpuPropState>({
  isReady: false,
  isFallback: false,
  isPaused: false,
  propRate: 1,
  satelliteCount: 0,
  simTime: new Date(),
  error: "",
})

const data: PropagationData = {
  positions: null,
  velocities: null,
  constantsByNorad: new Map(),
  count: 0,
}

// 内部非响应式状态
let propagator: any = null
let registeredSetId: number | null = null
let tleEpochJulians: Float64Array | null = null
let sessionStartSimTime = 0
let sessionStartWallMs = 0
let lastSimTime = 0
let propagatorInitPromise: Promise<void> | null = null
let propagationRafId = 0
let inflightRef = 0
let gpuConsecutiveFailures = 0
let refCount = 0
let initialized = false
let pendingSatellites: Satellite[] | null = null
let visibilityHandler: (() => void) | null = null

const MS_PER_DAY = 86400000

function dateToJulian(d: Date): number {
  return 2440587.5 + d.getTime() / MS_PER_DAY
}

function tleEpochToJulian(epochStr: string): number {
  const d = new Date(epochStr)
  return isNaN(d.getTime()) ? 0 : dateToJulian(d)
}

function getSimTimeMs(): number {
  if (state.isPaused || state.propRate === 0) return lastSimTime
  return sessionStartSimTime + (Date.now() - sessionStartWallMs) * state.propRate
}

function propagateCpu(simMs: number, constsList: any[]) {
  const simJulian = dateToJulian(new Date(simMs))
  const count = constsList.length
  if (data.positions === null || data.positions.length < count * 3) {
    data.positions = new Float32Array(count * 3)
    data.velocities = new Float32Array(count * 3)
  }
  const pos = data.positions
  const vel = data.velocities!
  data.count = count

  for (let i = 0; i < count; i++) {
    const minutesSinceEpoch = (simJulian - tleEpochJulians![i]) * 1440
    try {
      const pred = constsList[i].propagate(minutesSinceEpoch)
      const d = i * 3
      pos[d] = pred.position[0] * 1000
      pos[d + 1] = pred.position[1] * 1000
      pos[d + 2] = pred.position[2] * 1000
      vel[d] = pred.velocity[0] * 1000
      vel[d + 1] = pred.velocity[1] * 1000
      vel[d + 2] = pred.velocity[2] * 1000
    } catch {
      // 传播失败 -> 位置保持为 0（Cesium 中不可见）
    }
  }
}

let cpuConstants: any[] = []
const GPU_TIMEOUT_MS = 500
const GPU_MAX_FAILURES = 3

function propagationLoop() {
  if (!initialized) return

  const simMs = getSimTimeMs()
  lastSimTime = simMs
  state.simTime = new Date(simMs)

  const hasGpu = registeredSetId !== null && propagator
  const hasCpu = cpuConstants.length > 0

  if (!hasGpu && !hasCpu) {
    propagationRafId = requestAnimationFrame(propagationLoop)
    return
  }

  if (inflightRef > 0) {
    propagationRafId = requestAnimationFrame(propagationLoop)
    return
  }

  if (state.isFallback || !propagator) {
    propagateCpu(simMs, cpuConstants)
    propagationRafId = requestAnimationFrame(propagationLoop)
    return
  }

  // GPU 传播
  inflightRef++
  const simJulian = dateToJulian(new Date(simMs))

  const times = new Float64Array(tleEpochJulians!.length)
  for (let i = 0; i < times.length; i++) {
    times[i] = (simJulian - tleEpochJulians![i]) * 1440
  }

  // 超时保护：GPU 挂死时自动触发 CPU 回退
  const gpuPromise = propagator.propagate_registered_f32(registeredSetId, times)
  const timeoutPromise = new Promise<Float32Array>((_, reject) =>
    setTimeout(() => reject(new Error("GPU 传播超时")), GPU_TIMEOUT_MS),
  )

  Promise.race([gpuPromise, timeoutPromise])
    .then((flat: Float32Array) => {
      gpuConsecutiveFailures = 0
      const satCount = flat.length / 6
      if (data.positions === null || data.positions.length !== satCount * 3) {
        data.positions = new Float32Array(satCount * 3)
        data.velocities = new Float32Array(satCount * 3)
      }
      const pos = data.positions
      const vel = data.velocities!
      data.count = satCount
      for (let i = 0; i < satCount; i++) {
        const o = i * 6, d = i * 3
        pos[d] = flat[o] * 1000
        pos[d + 1] = flat[o + 1] * 1000
        pos[d + 2] = flat[o + 2] * 1000
        vel[d] = flat[o + 3] * 1000
        vel[d + 1] = flat[o + 4] * 1000
        vel[d + 2] = flat[o + 5] * 1000
      }
      inflightRef--
    })
    .catch((err: any) => {
      console.error("[useGpuPropagation] GPU 传播失败:", err)
      gpuConsecutiveFailures++
      if (gpuConsecutiveFailures >= GPU_MAX_FAILURES) {
        state.error = "GPU 连续失败，已回退到 CPU"
        state.isFallback = true
        cpuConstants = [...data.constantsByNorad.values()]
        console.warn("[useGpuPropagation] 回退到 CPU")
      }
      inflightRef--
    })

  propagationRafId = requestAnimationFrame(propagationLoop)
}

async function initPropagator() {
  if (propagatorInitPromise) return propagatorInitPromise

  propagatorInitPromise = (async () => {
    try {
      await wasmInit(wasmUrl)

      try {
        propagator = await GpuPropagator.new_for_web()
      } catch {
        try {
          propagator = await GpuPropagator.new_for_web_gl()
        } catch {
          state.isFallback = true
          console.info("[useGpuPropagation] WebGPU/WebGL 不可用，使用 CPU 回退")
        }
      }

      const now = Date.now()
      sessionStartSimTime = now
      sessionStartWallMs = now
      lastSimTime = now
      state.isReady = true
      state.simTime = new Date(now)

      visibilityHandler = () => {
        if (document.hidden) {
          cancelAnimationFrame(propagationRafId)
          propagationRafId = 0
        } else if (propagationRafId === 0) {
          propagationRafId = requestAnimationFrame(propagationLoop)
        }
      }
      document.addEventListener("visibilitychange", visibilityHandler)

      if (pendingSatellites) {
        registerSatellites(pendingSatellites)
      }
      propagationRafId = requestAnimationFrame(propagationLoop)
    } catch (err: any) {
      state.error = `sgp4.gl 初始化失败: ${err.message || err}`
      console.error("[useGpuPropagation]", state.error)
    }
  })()

  return propagatorInitPromise
}

async function registerSatellites(sats: Satellite[]) {
  if (!state.isReady) {
    pendingSatellites = sats
    return
  }
  pendingSatellites = null

  if (registeredSetId !== null && propagator) {
    try { propagator.unregister_const_set(registeredSetId) } catch { /* ok */ }
    registeredSetId = null
  }
  cpuConstants = []
  tleEpochJulians = null

  if (sats.length === 0) {
    data.positions = null
    data.velocities = null
    data.count = 0
    state.satelliteCount = 0
    return
  }

  const elements: any[] = []
  const epochs: number[] = []
  const norads: number[] = []

  for (const sat of sats) {
    if (!sat.tle1 || !sat.tle2) continue
    try {
      const el = WasmElements.from_tle(
        new TextEncoder().encode(sat.name),
        new TextEncoder().encode(sat.tle1),
        new TextEncoder().encode(sat.tle2),
      )
      elements.push(el)
      epochs.push(tleEpochToJulian(sat.epoch))
      norads.push(sat.norad)
    } catch (err) {
      console.warn(`[useGpuPropagation] 跳过 ${sat.norad}: TLE 解析失败`, err)
    }
  }

  state.satelliteCount = elements.length
  tleEpochJulians = new Float64Array(epochs)

  data.positions = null
  data.velocities = null
  data.count = 0
  data.constantsByNorad.clear()

  if (elements.length === 0) {
    return
  }

  const constants = elements.map((el: any) => WasmConstants.from_elements(el))
  for (let i = 0; i < norads.length; i++) {
    data.constantsByNorad.set(norads[i], constants[i])
  }

  if (state.isFallback || !propagator) {
    cpuConstants = constants
    return
  }

  try {
    const gpuConsts = constants.map((c: any) => WasmGpuConsts.from_constants(c))
    registeredSetId = propagator.register_const_set(gpuConsts)
  } catch (err) {
    console.error("[useGpuPropagation] 注册 GPU 传播集失败:", err)
    state.isFallback = true
    cpuConstants = constants
  }
}

function setPropRate(rate: number) {
  if (state.isPaused) return
  const now = Date.now()
  sessionStartSimTime = lastSimTime
  sessionStartWallMs = now
  state.propRate = rate
}

function togglePause() {
  if (state.isPaused) {
    sessionStartSimTime = lastSimTime
    sessionStartWallMs = Date.now()
    state.isPaused = false
  } else {
    lastSimTime = getSimTimeMs()
    state.isPaused = true
  }
}

function resetTime() {
  const now = Date.now()
  sessionStartSimTime = now
  sessionStartWallMs = now
  lastSimTime = now
  state.propRate = 1
  state.isPaused = false
  state.simTime = new Date(now)
}

function jumpToMinutes(deltaMinutes: number) {
  const simMs = getSimTimeMs() + deltaMinutes * 60000
  sessionStartSimTime = simMs
  sessionStartWallMs = Date.now()
  lastSimTime = simMs
}

function setTimeOffset(offsetMs: number) {
  const now = Date.now()
  const targetMs = now + offsetMs
  sessionStartSimTime = targetMs
  sessionStartWallMs = now
  lastSimTime = targetMs
}

function dispose() {
  cancelAnimationFrame(propagationRafId)
  propagationRafId = 0
  if (visibilityHandler) {
    document.removeEventListener("visibilitychange", visibilityHandler)
    visibilityHandler = null
  }
  if (registeredSetId !== null && propagator) {
    try { propagator.unregister_const_set(registeredSetId) } catch { /* ok */ }
    registeredSetId = null
  }
  propagator = null
  cpuConstants = []
  tleEpochJulians = null
  data.positions = null
  data.velocities = null
  data.constantsByNorad.clear()
  data.count = 0
  state.isReady = false
  state.isFallback = false
  state.isPaused = false
  state.propRate = 1
  state.satelliteCount = 0
  state.error = ""
  propagatorInitPromise = null
  initialized = false
  inflightRef = 0
  gpuConsecutiveFailures = 0
  pendingSatellites = null
}

export function useGpuPropagation() {
  onMounted(() => {
    refCount++
    if (!initialized) {
      initialized = true
      initPropagator()
    }
  })

  onUnmounted(() => {
    refCount--
    if (refCount <= 0) {
      dispose()
    }
  })

  return {
    state,
    data,
    registerSatellites,
    setPropRate,
    togglePause,
    resetTime,
    jumpToMinutes,
    setTimeOffset,
  }
}
