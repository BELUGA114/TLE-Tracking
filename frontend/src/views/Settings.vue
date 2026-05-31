<template>
  <div>
    <h2 class="page-title">设置</h2>
    <p class="page-desc">修改以下配置后点击保存，将在下一轮询周期自动生效，无需重启容器。</p>

    <div v-if="loading" class="loading">加载中...</div>

    <form v-else @submit.prevent="save" class="settings-form">
      <fieldset>
        <legend>监控目标</legend>
        <label>
          <span>NORAD IDs</span>
          <span class="hint">逗号分隔，例如: 25544, 48273</span>
        </label>
        <input
          v-model="form.norad_ids_str"
          type="text"
          placeholder="25544"
          class="input"
        />
      </fieldset>

      <fieldset>
        <legend>告警</legend>
        <div class="row">
          <label>
            <span>再入预警高度 (km)</span>
            <span class="hint">近地点低于此值时触发预警</span>
          </label>
          <input v-model.number="form.alerts_reentry_warning_km" type="number" class="input input-sm" />
        </div>
        <div class="row">
          <label>
            <span>降级机动阈值 (km)</span>
            <span class="hint">xpropagator 不可用时，近地点/远地点变化超过此值视为机动</span>
          </label>
          <input v-model.number="form.alerts_fallback_threshold" type="number" step="0.1" class="input input-sm" />
        </div>
        <div class="row checkbox-row">
          <label>
            <span>仅在 TLE 变化时打印</span>
          </label>
          <input v-model="form.alerts_only_print_on_update" type="checkbox" />
        </div>
      </fieldset>

      <fieldset>
        <legend>xpropagator 残差分析</legend>
        <div class="row checkbox-row">
          <label>
            <span>启用 xpropagator</span>
            <span class="hint">关闭后使用简单阈值判定机动</span>
          </label>
          <input v-model="form.xprop_enabled" type="checkbox" />
        </div>
        <div class="row">
          <label>
            <span>机动判定阈值 (km)</span>
            <span class="hint">残差超过此值视为真实机动</span>
          </label>
          <input v-model.number="form.xprop_maneuver_threshold" type="number" step="0.1" class="input input-sm" />
        </div>
      </fieldset>

      <fieldset>
        <legend>数据源</legend>
        <div class="row">
          <label>
            <span>备源切换失败次数</span>
            <span class="hint">主源连续失败此次数后切换到备源</span>
          </label>
          <input v-model.number="form.ds_fallback_threshold" type="number" class="input input-sm" />
        </div>
      </fieldset>

      <fieldset class="readonly-section">
        <legend>需手动编辑 config.yaml 后重启</legend>
        <div class="readonly-grid">
          <div class="ro-item">
            <span class="ro-key">files.*</span>
            <span class="ro-reason">数据目录、文件名等路径配置</span>
          </div>
          <div class="ro-item">
            <span class="ro-key">data_source.primary / fallback</span>
            <span class="ro-reason">双源切换路径</span>
          </div>
          <div class="ro-item">
            <span class="ro-key">data_source.celestrak_interval_seconds</span>
            <span class="ro-reason">涉及 API 速率合规</span>
          </div>
          <div class="ro-item">
            <span class="ro-key">retry.*</span>
            <span class="ro-reason">登录/请求重试参数</span>
          </div>
          <div class="ro-item">
            <span class="ro-key">xpropagator.host / port</span>
            <span class="ro-reason">gRPC 连接地址</span>
          </div>
        </div>
      </fieldset>

      <div class="actions">
        <button type="submit" class="btn-save" :disabled="saving">
          {{ saving ? "保存中..." : "保存配置" }}
        </button>
        <span v-if="saved" class="saved-msg">已保存，将在下一轮询周期生效</span>
        <span v-if="error" class="error-msg">{{ error }}</span>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from "vue"

interface ConfigForm {
  norad_ids_str: string
  alerts_reentry_warning_km: number
  alerts_only_print_on_update: boolean
  alerts_fallback_threshold: number
  xprop_enabled: boolean
  xprop_maneuver_threshold: number
  ds_fallback_threshold: number
}

const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref("")

const form = reactive<ConfigForm>({
  norad_ids_str: "",
  alerts_reentry_warning_km: 200,
  alerts_only_print_on_update: true,
  alerts_fallback_threshold: 5.0,
  xprop_enabled: true,
  xprop_maneuver_threshold: 5.0,
  ds_fallback_threshold: 3,
})

async function loadConfig() {
  loading.value = true
  error.value = ""
  try {
    const resp = await fetch("/api/config")
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const cfg = await resp.json()

    form.norad_ids_str = (cfg.targets?.norad_ids || []).join(", ")
    form.alerts_reentry_warning_km = cfg.alerts?.reentry_warning_km ?? 200
    form.alerts_only_print_on_update = cfg.alerts?.only_print_on_update ?? true
    form.alerts_fallback_threshold = cfg.alerts?.fallback_maneuver_threshold_km ?? 5.0
    form.xprop_enabled = cfg.xpropagator?.enabled ?? true
    form.xprop_maneuver_threshold = cfg.xpropagator?.maneuver_threshold_km ?? 5.0
    form.ds_fallback_threshold = cfg.data_source?.fallback_threshold ?? 3
  } catch (e: any) {
    error.value = `加载配置失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

function parseNoradIds(raw: string): number[] {
  return raw
    .split(/[,，\s]+/)
    .map(s => s.trim())
    .filter(s => s.length > 0)
    .map(Number)
    .filter(n => Number.isInteger(n) && n > 0)
}

async function save() {
  saving.value = true
  saved.value = false
  error.value = ""

  const norad_ids = parseNoradIds(form.norad_ids_str)
  if (norad_ids.length === 0) {
    error.value = "NORAD IDs 不能为空"
    saving.value = false
    return
  }

  const payload = {
    targets: { norad_ids },
    alerts: {
      reentry_warning_km: form.alerts_reentry_warning_km,
      only_print_on_update: form.alerts_only_print_on_update,
      fallback_maneuver_threshold_km: form.alerts_fallback_threshold,
    },
    xpropagator: {
      enabled: form.xprop_enabled,
      maneuver_threshold_km: form.xprop_maneuver_threshold,
    },
    data_source: {
      fallback_threshold: form.ds_fallback_threshold,
    },
  }

  try {
    const resp = await fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
    if (!resp.ok) {
      const body = await resp.json()
      throw new Error(body.detail || `HTTP ${resp.status}`)
    }
    saved.value = true
  } catch (e: any) {
    error.value = `保存失败: ${e.message}`
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.page-desc {
  color: #94a3b8;
  margin-bottom: 1.5rem;
  font-size: 0.9rem;
}
.loading {
  color: #94a3b8;
}
.settings-form {
  max-width: 640px;
}
fieldset {
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 1.25rem;
  margin-bottom: 1.25rem;
}
legend {
  color: #38bdf8;
  font-weight: 600;
  padding: 0 0.5rem;
}
label {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  margin-bottom: 0.75rem;
  color: #e2e8f0;
  font-size: 0.9rem;
}
.hint {
  color: #64748b;
  font-size: 0.78rem;
  font-weight: 400;
}
.row {
  margin-bottom: 0.75rem;
}
.checkbox-row label {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}
.input {
  width: 100%;
  padding: 0.45rem 0.6rem;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 4px;
  color: #e2e8f0;
  font-size: 0.9rem;
}
.input:focus {
  outline: none;
  border-color: #0ea5e9;
}
.input-sm {
  max-width: 160px;
}
input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: #0ea5e9;
}
.readonly-section legend {
  color: #64748b;
}
.readonly-grid {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.ro-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.35rem 0;
  border-bottom: 1px solid #1e293b;
}
.ro-key {
  color: #94a3b8;
  font-size: 0.85rem;
  font-family: monospace;
}
.ro-reason {
  color: #64748b;
  font-size: 0.78rem;
}
.actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1.5rem;
}
.btn-save {
  padding: 0.5rem 1.5rem;
  background: #0ea5e9;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  cursor: pointer;
}
.btn-save:hover {
  background: #0284c7;
}
.btn-save:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.saved-msg {
  color: #4ade80;
  font-size: 0.85rem;
}
.error-msg {
  color: #f87171;
  font-size: 0.85rem;
}
</style>
