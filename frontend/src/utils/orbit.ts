/**
 * 从轨道根数计算卫星在当前时刻的近似 ECEF 位置。
 * 使用圆轨道简化 + GMST 旋转，Phase 2 将由 sgp4.gl 替代。
 */

import type { Satellite } from "../types"

export interface PositionEcef {
  x: number
  y: number
  z: number
}

/**
 * 检查位置是否有效（非 NaN、非无穷、非原点）
 */
function isValidPosition(pos: PositionEcef): boolean {
  if (!Number.isFinite(pos.x) || !Number.isFinite(pos.y) || !Number.isFinite(pos.z)) {
    return false
  }
  // 距地心至少 1 km（1000 m），排除原点
  const distSq = pos.x * pos.x + pos.y * pos.y + pos.z * pos.z
  return distSq > 1e6
}

function gmstDeg(jd: number): number {
  const T = (jd - 2451545.0) / 36525
  let g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T - T * T * T / 38710000
  g = g % 360
  return g < 0 ? g + 360 : g
}

function epochToJd(epoch: string): number | null {
  const d = new Date(epoch)
  if (isNaN(d.getTime())) return null
  const y = d.getUTCFullYear()
  const m = d.getUTCMonth() + 1
  const day = d.getUTCDate()
  const h = d.getUTCHours()
  const min = d.getUTCMinutes()
  const s = d.getUTCSeconds() + d.getUTCMilliseconds() / 1000

  const a = Math.floor((14 - m) / 12)
  const y2 = y + 4800 - a
  const m2 = m + 12 * a - 3
  let jd = day + Math.floor((153 * m2 + 2) / 5) + 365 * y2 + Math.floor(y2 / 4) - Math.floor(y2 / 100) + Math.floor(y2 / 400) - 32045
  jd += (h - 12) / 24 + min / 1440 + s / 86400
  return jd
}

function orbitalToEci(
  meanMotionRevPerDay: number,
  eccentricity: number,
  inclDeg: number,
  raanDeg: number,
  argPerigeeDeg: number,
  meanAnomalyDeg: number,
  deltaDays: number,
): { x: number; y: number; z: number } {
  const mu = 398600.4418
  const nRadPerSec = meanMotionRevPerDay * 2 * Math.PI / 86400
  const semiMajor = Math.cbrt(mu / (nRadPerSec * nRadPerSec))

  const currentMa = ((meanAnomalyDeg + meanMotionRevPerDay * 360 * deltaDays) % 360 + 360) % 360

  let E = currentMa * Math.PI / 180
  for (let i = 0; i < 3; i++) {
    E = currentMa * Math.PI / 180 + eccentricity * Math.sin(E)
  }

  const cosE = Math.cos(E)
  const sinE = Math.sin(E)
  const sqrt1me2 = Math.sqrt(1 - eccentricity * eccentricity)

  const xOrb = semiMajor * (cosE - eccentricity)
  const yOrb = semiMajor * sqrt1me2 * sinE

  const i = inclDeg * Math.PI / 180
  const Ω = raanDeg * Math.PI / 180
  const ω = argPerigeeDeg * Math.PI / 180

  const cosΩ = Math.cos(Ω); const sinΩ = Math.sin(Ω)
  const cosω = Math.cos(ω); const sinω = Math.sin(ω)
  const cosi = Math.cos(i); const sini = Math.sin(i)

  const R11 = cosΩ * cosω - sinΩ * sinω * cosi
  const R12 = -cosΩ * sinω - sinΩ * cosω * cosi
  const R21 = sinΩ * cosω + cosΩ * sinω * cosi
  const R22 = -sinΩ * sinω + cosΩ * cosω * cosi
  const R31 = sinω * sini
  const R32 = cosω * sini

  return {
    x: R11 * xOrb + R12 * yOrb,
    y: R21 * xOrb + R22 * yOrb,
    z: R31 * xOrb + R32 * yOrb,
  }
}

export function computeSatellitePosition(sat: Satellite, now: Date): PositionEcef | null {
  const jdNow = epochToJd(now.toISOString())
  const jdEpoch = epochToJd(sat.epoch)
  if (jdNow === null || jdEpoch === null) return null

  const deltaDays = jdNow - jdEpoch

  // 平均运动必须有效（> 0），否则无法计算
  const mm = sat.MEAN_MOTION || (sat.period > 0 ? 1440 / sat.period : 0)
  if (mm <= 0) return null

  const ecc = Math.min(sat.ecc || 0, 0.99)  // 偏高心率截断，防止开普勒迭代发散
  const incl = sat.incl
  const raan = sat.RA_OF_ASC_NODE || 0
  const argPeri = sat.ARG_OF_PERICENTER || 0
  const ma = sat.MEAN_ANOMALY || 0

  const eci = orbitalToEci(mm, ecc, incl, raan, argPeri, ma, deltaDays)

  const θ = gmstDeg(jdNow) * Math.PI / 180
  const cosθ = Math.cos(θ); const sinθ = Math.sin(θ)

  const pos: PositionEcef = {
    x: (eci.x * cosθ + eci.y * sinθ) * 1000,
    y: (-eci.x * sinθ + eci.y * cosθ) * 1000,
    z: eci.z * 1000,
  }

  return isValidPosition(pos) ? pos : null
}

export function computeAllPositions(sats: Satellite[], now: Date): (PositionEcef | null)[] {
  return sats.map(sat => computeSatellitePosition(sat, now))
}
