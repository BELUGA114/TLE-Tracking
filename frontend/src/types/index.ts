export interface Satellite {
  timestamp: string
  change_type: "initial" | "correction" | "maneuver"
  source: string
  norad: number
  name: string
  intl_id: string
  epoch: string
  periapsis: number
  apoapsis: number
  incl: number
  period: number
  ecc: number
  bstar: number
  tle1: string
  tle2: string
  tle_hash: string
  // merged from _raw_elements
  RA_OF_ASC_NODE: number
  ARG_OF_PERICENTER: number
  MEAN_ANOMALY: number
  MEAN_MOTION: number
  MEAN_MOTION_DOT: number
  MEAN_MOTION_DDOT: number
  REV_AT_EPOCH: number
  ELEMENT_SET_NO: number
  CLASSIFICATION_TYPE: string
}

export interface DecaySatellite {
  norad: number
  name: string
  phase: "normal" | "early_decay" | "accelerating" | "critical"
  periapsis?: number
  apoapsis?: number
}

export interface HistoryRecord extends Satellite {}

export interface SatellitesResponse {
  satellites: Satellite[]
  total: number
}

export interface DecayResponse {
  satellites: DecaySatellite[]
  total: number
}

export interface HistoryResponse {
  changes: HistoryRecord[]
  total: number
}
