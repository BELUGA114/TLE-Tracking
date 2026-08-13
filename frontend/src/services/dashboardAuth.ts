const STORAGE_KEY = "tle-tracking.dashboard-api-key"

export function loadDashboardApiKey(): string {
  return localStorage.getItem(STORAGE_KEY) ?? ""
}

export function saveDashboardApiKey(value: string): void {
  const normalized = value.trim()
  if (!normalized) {
    localStorage.removeItem(STORAGE_KEY)
    return
  }
  localStorage.setItem(STORAGE_KEY, normalized)
}

export function clearDashboardApiKey(): void {
  localStorage.removeItem(STORAGE_KEY)
}

export function dashboardAuthHeaders(): Record<string, string> {
  const apiKey = loadDashboardApiKey()
  return apiKey ? { Authorization: `Bearer ${apiKey}` } : {}
}
