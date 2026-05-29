import type { SatellitesResponse, DecayResponse, HistoryResponse } from "../types"

const BASE = "/api"

async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`)
  return res.json()
}

export function fetchSatellites(): Promise<SatellitesResponse> {
  return fetchJSON(`${BASE}/satellites`)
}

export function fetchSatellite(noradId: number): Promise<SatellitesResponse> {
  return fetchJSON(`${BASE}/satellites/${noradId}`)
}

export function fetchDecayStatus(): Promise<DecayResponse> {
  return fetchJSON(`${BASE}/decay`)
}

export function fetchHistory(limit = 100): Promise<HistoryResponse> {
  return fetchJSON(`${BASE}/history/changes?limit=${limit}`)
}
