/**
 * OrbitPathComputer — 从 SGP4 常数计算轨道线 TEME 坐标采样点。
 * 纯函数：给定输入，返回 Cartesian3[]，无副作用。
 *
 * 算法说明：
 * - LEO/MEO (ecc < 0.2)：等时间采样 16 点，覆盖约 1 个轨道周期
 * - HEO (ecc >= 0.2)：等真近点角采样 32 点，近地点加密
 * - 三次埃尔米特插值：利用 SGP4 速度作为切线平滑段间过渡
 */
import type * as Cesium from "cesium"
import type { Satellite } from "../types"

/**
 * SGP4 常数实例的结构接口。
 * 对应 useGpuPropagation 中 data.constantsByNorad 的 value 类型。
 * 只声明 propagate 方法签名——任何匹配此签名的对象均可传入。
 */
export interface Sgp4Constants {
  propagate(minutesSinceEpoch: number): {
    position: [number, number, number]
    velocity: [number, number, number]
  }
}

function dateToJulian(d: Date): number {
  return 2440587.5 + d.getTime() / 86400000
}

/**
 * Newton-Raphson 求解开普勒方程 M = E - e·sin(E)，转为真近点角 ν。
 * 返回未归化的 ν（保留圈数），避免大时间跨度下 ν 被折叠到 [-π, π]。
 */
function meanAnomalyToTrueAnomaly(M_rad: number, ecc: number): number {
  const M_wrapped = ((M_rad % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)
  const rev = M_rad - M_wrapped
  let E = M_wrapped
  for (let i = 0; i < 20; i++) {
    const dE = (M_wrapped - E + ecc * Math.sin(E)) / (1 - ecc * Math.cos(E))
    E += dE
    if (Math.abs(dE) < 1e-14) break
  }
  const sinNu = Math.sqrt(1 - ecc * ecc) * Math.sin(E) / (1 - ecc * Math.cos(E))
  const cosNu = (Math.cos(E) - ecc) / (1 - ecc * Math.cos(E))
  return Math.atan2(sinNu, cosNu) + rev
}

/** 单次传播结果 */
interface PropagationSample {
  pos: [number, number, number]
  vel: [number, number, number]
  dtSec: number
}

/** 尝试以指定 offset 为中心计算轨道线。失败返回 null。 */
function tryComputePath(
  consts: Sgp4Constants,
  sat: Satellite,
  meanMotion: number,
  ecc: number,
  periodMinutes: number,
  _epochJulian: number,
  centerOffsetDays: number,
  CesiumModule: typeof Cesium,
): Cesium.Cartesian3[] | null {
  try {
    const centerMinutesSinceEpoch = centerOffsetDays * 1440
    const useTrueAnomaly = ecc >= 0.2
    const numSamples = useTrueAnomaly ? 32 : 16
    const subSteps = 8
    const raw: PropagationSample[] = []

    if (useTrueAnomaly) {
      const M0_deg = parseFloat(sat.tle2.substring(43, 51).trim()) || 0
      const M0_rad = (M0_deg * Math.PI) / 180
      const nRadPerMin = (meanMotion * 2 * Math.PI) / 1440
      const M_sim = M0_rad + nRadPerMin * centerMinutesSinceEpoch
      const nu_sim = meanAnomalyToTrueAnomaly(M_sim, ecc)

      for (let j = 0; j <= numSamples; j++) {
        const nu = nu_sim + 2 * Math.PI * (j / numSamples - 0.5)
        const sinNu2 = Math.sin(nu / 2)
        const cosNu2 = Math.cos(nu / 2)
        let E =
          2 *
          Math.atan2(
            Math.sqrt((1 - ecc) / (1 + ecc)) * sinNu2,
            cosNu2,
          )
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
        const minutesSinceEpoch =
          centerMinutesSinceEpoch - halfPeriod + (j / numSamples) * periodMinutes
        const pred = consts.propagate(minutesSinceEpoch)
        raw.push({
          pos: [pred.position[0] * 1000, pred.position[1] * 1000, pred.position[2] * 1000],
          vel: [pred.velocity[0] * 1000, pred.velocity[1] * 1000, pred.velocity[2] * 1000],
          dtSec: minutesSinceEpoch * 60,
        })
      }
    }

    if (raw.length < 2) return null

    // 三次埃尔米特插值
    const posArray: number[] = []
    for (let j = 0; j < numSamples; j++) {
      const s0 = raw[j]
      const s1 = raw[j + 1]
      const dt = s1.dtSec - s0.dtSec
      const p0 = s0.pos
      const v0 = s0.vel
      const p1 = s1.pos
      const v1 = s1.vel
      for (let k = 0; k < subSteps; k++) {
        const t = k / subSteps
        const t2 = t * t
        const t3 = t2 * t
        const h00 = 2 * t3 - 3 * t2 + 1
        const h10 = t3 - 2 * t2 + t
        const h01 = -2 * t3 + 3 * t2
        const h11 = t3 - t2
        posArray.push(
          h00 * p0[0] + h10 * v0[0] * dt + h01 * p1[0] + h11 * v1[0] * dt,
          h00 * p0[1] + h10 * v0[1] * dt + h01 * p1[1] + h11 * v1[1] * dt,
          h00 * p0[2] + h10 * v0[2] * dt + h01 * p1[2] + h11 * v1[2] * dt,
        )
      }
    }
    const lastRaw = raw[raw.length - 1]
    posArray.push(lastRaw.pos[0], lastRaw.pos[1], lastRaw.pos[2])

    if (posArray.length < 9) return null

    const cartesians = new Array<Cesium.Cartesian3>(posArray.length / 3)
    for (let j = 0; j < cartesians.length; j++) {
      cartesians[j] = new CesiumModule.Cartesian3(
        posArray[j * 3],
        posArray[j * 3 + 1],
        posArray[j * 3 + 2],
      )
    }

    return cartesians
  } catch {
    return null
  }
}

/**
 * 计算单颗卫星的轨道线采样点。
 * @param consts - SGP4 常数实例（来自 useGpuPropagation.data.constantsByNorad）
 * @param sat - 卫星 TLE 数据
 * @param simTime - 当前仿真时间
 * @param CesiumModule - Cesium 模块引用（避免循环依赖）
 * @returns Cartesian3 数组（TEME 坐标，单位 m），失败返回 null
 */
export function computeOrbitPath(
  consts: Sgp4Constants,
  sat: Satellite,
  simTime: Date,
  CesiumModule: typeof Cesium,
): Cesium.Cartesian3[] | null {
  if (!sat.tle1 || !sat.tle2) return null

  try {
    const meanMotion = parseFloat(sat.tle2.substring(51, 63).trim())
    if (meanMotion <= 0) return null

    const periodMinutes = 1440 / meanMotion
    const ecc = sat.ecc || 0

    const epochDate = new Date(sat.epoch)
    if (isNaN(epochDate.getTime())) return null

    const epochJulian = dateToJulian(epochDate)
    const simJulian = dateToJulian(simTime)

    // 优先以 simTime 为中心采样（轨道面与当前点位置一致）。
    // 若 simTime 距 epoch 太远导致 SGP4 数值溢出，回退到 epoch 附近采样。
    for (const centerOffset of [simJulian - epochJulian, 0]) {
      const result = tryComputePath(
        consts, sat, meanMotion, ecc, periodMinutes, epochJulian,
        centerOffset, CesiumModule,
      )
      if (result) return result
    }
    return null
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[OrbitPathComputer] 轨道计算失败 [${sat.norad}]: ${msg}`)
    return null
  }
}
