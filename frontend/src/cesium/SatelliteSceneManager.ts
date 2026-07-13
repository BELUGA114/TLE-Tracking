/**
 * SatelliteSceneManager — KeepTrack 风格的卫星场景管理器。
 *
 * 设计原则（照抄 KeepTrack.space 的 dots-manager + line-manager 模式）：
 * 1. 数组索引 = 卫星身份。不维护 Map<norad, Entity>，只用平行数组。
 * 2. 单次全量重建：卫星列表变化时 wipe-all + rebuild-all，帧内不做增量 diff。
 * 3. 每帧只更新点位置（直接按索引写入 Cartesian3），零 Map 查找。
 * 4. 轨道线只在 TLE 变化或 10min 超时后重建，形状在 TEME 系中保持静态。
 */
import type * as Cesium from "cesium"
import type { Satellite } from "../types"
import { computeOrbitPath, type Sgp4Constants } from "./OrbitPathComputer"

/** 平行数组：卫星点 + 轨道线，按注册索引对齐 */
interface OrbitSlot {
  polyline: Cesium.Polyline | null
  lastRefreshSimMs: number
}

export class SatelliteSceneManager {
  private pointCollection: Cesium.PointPrimitiveCollection
  private polylineCollection: Cesium.PolylineCollection

  /** norad → 在 pointCollection / orbitSlots 中的索引 */
  private noradToIdx = new Map<number, number>()
  private orbitSlots: OrbitSlot[] = []

  /** 复用的 Cartesian3 数组，每帧只改 x/y/z，不分配 */
  private scratchPositions: Cesium.Cartesian3[] = []

  private C: typeof Cesium

  constructor(scene: Cesium.Scene, CesiumModule: typeof Cesium) {
    this.C = CesiumModule
    this.pointCollection = scene.primitives.add(new CesiumModule.PointPrimitiveCollection())
    this.polylineCollection = scene.primitives.add(new CesiumModule.PolylineCollection())
    this.pointCollection.modelMatrix = CesiumModule.Matrix4.IDENTITY
    this.polylineCollection.modelMatrix = CesiumModule.Matrix4.IDENTITY
  }

  /** 全量重建：wipe → rebuild。只在卫星列表变化时调用。 */
  rebuild(
    satellites: Satellite[],
    constantsByNorad: ReadonlyMap<number, Sgp4Constants>,
    simTime: Date,
  ): void {
    const C = this.C
    const simMs = simTime.getTime()

    // 1. Wipe
    this.pointCollection.removeAll()
    this.polylineCollection.removeAll()
    this.noradToIdx.clear()
    this.orbitSlots = []
    this.scratchPositions = []

    // 2. Rebuild：按 constantsByNorad key 顺序（= 注册顺序 = data.positions 顺序）
    let idx = 0
    for (const norad of constantsByNorad.keys()) {
      this.noradToIdx.set(norad, idx)

      // Point
      const point = this.pointCollection.add({
        position: C.Cartesian3.ZERO,
        color: C.Color.fromCssColorString("#4ade80"),
        pixelSize: 5,
        outlineColor: C.Color.fromCssColorString("#166534"),
        outlineWidth: 1,
      })
      this.scratchPositions.push(new C.Cartesian3())

      // Orbit path
      const sat = satellites.find((s) => s.norad === norad)
      const consts = constantsByNorad.get(norad)
      let polyline: Cesium.Polyline | null = null

      if (sat && consts) {
        const positions = computeOrbitPath(consts, sat, simTime, C)
        if (positions && positions.length >= 2) {
          polyline = this.polylineCollection.add({ positions, width: 1 })
          polyline.material = C.Material.fromType("Color")
          ;(polyline.material as Cesium.Material).uniforms.color = new C.Color(
            0.29, 0.83, 0.5, 0.3,
          )
        }
      }

      this.orbitSlots.push({ polyline, lastRefreshSimMs: simMs })
      idx++
    }
  }

  /** 每帧调用：按索引直接写入位置，零 Map 查找 */
  updatePoints(positions: Float32Array, count: number): void {
    const n = Math.min(count, this.scratchPositions.length)
    for (let i = 0; i < n; i++) {
      const o = i * 3
      const point = this.pointCollection.get(i)
      // SGP4 传播失败时位置保持为 0（useGpuPropagation CPU 回退行为）。
      // 原点在地心会导致卫星粘在相机视点中心——隐藏该点。
      if (positions[o] === 0 && positions[o + 1] === 0 && positions[o + 2] === 0) {
        point.show = false
        continue
      }
      point.show = true
      const pos = this.scratchPositions[i]
      pos.x = positions[o]
      pos.y = positions[o + 1]
      pos.z = positions[o + 2]
      point.position = pos
    }
  }

  /**
   * 检查并刷新过期轨道线（>10min）或补建缺失的。
   * 每帧 preRender 中调用。
   */
  refreshStaleOrbits(
    satellites: Satellite[],
    constantsByNorad: ReadonlyMap<number, Sgp4Constants>,
    simTime: Date,
    thresholdMs: number = 600000,
  ): void {
    const C = this.C
    const simMs = simTime.getTime()

    for (const sat of satellites) {
      const idx = this.noradToIdx.get(sat.norad)
      if (idx === undefined || idx >= this.orbitSlots.length) continue

      const slot = this.orbitSlots[idx]
      const needsRefresh =
        slot.polyline === null ||
        Math.abs(simMs - slot.lastRefreshSimMs) > thresholdMs

      if (!needsRefresh) continue

      const consts = constantsByNorad.get(sat.norad)
      if (!consts) continue

      // 移除旧线
      if (slot.polyline) {
        this.polylineCollection.remove(slot.polyline)
        slot.polyline = null
      }

      const positions = computeOrbitPath(consts, sat, simTime, C)
      if (positions && positions.length >= 2) {
        const poly = this.polylineCollection.add({ positions, width: 1 })
        poly.material = C.Material.fromType("Color")
        ;(poly.material as Cesium.Material).uniforms.color = new C.Color(
          0.29, 0.83, 0.5, 0.3,
        )
        slot.polyline = poly
        slot.lastRefreshSimMs = simMs
      }
    }
  }

  get pointCount(): number {
    return this.scratchPositions.length
  }

  get orbitCount(): number {
    return this.orbitSlots.filter((s) => s.polyline !== null).length
  }

  dispose(): void {
    this.pointCollection.removeAll()
    this.polylineCollection.removeAll()
    this.noradToIdx.clear()
    this.orbitSlots = []
    this.scratchPositions = []
  }
}
