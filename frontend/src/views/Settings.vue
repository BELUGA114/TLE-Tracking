<template>
  <div>
    <h2 class="page-title">设置</h2>
    <p class="page-desc">修改以下配置后点击保存，将在下一轮询周期自动生效，无需重启容器。</p>

    <div v-if="loading">
      <div class="skeleton skeleton-card" style="margin-bottom:0.75rem;"></div>
      <div class="skeleton skeleton-card" style="margin-bottom:0.75rem;"></div>
      <div class="skeleton skeleton-card" style="height:80px;"></div>
    </div>

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
            <span>SGP4 可靠高度下限 (km)</span>
            <span class="hint">近地点低于此值时跳过残差分析，仅使用简单阈值判定</span>
          </label>
          <input v-model.number="form.alerts_sgp4_reliable_floor_km" type="number" class="input input-sm" />
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

      <fieldset>
        <legend>新对象发现</legend>
        <p style="color: var(--color-text-muted); font-size: 0.8rem; margin-bottom: 0.75rem;">
          每天 17:10 UTC 检查 Space-Track SATCAT 新编目 PAYLOAD 对象，通过 Telegram 推送通知。
        </p>
        <div class="row checkbox-row">
          <label>
            <span>启用新对象发现</span>
            <span class="hint">打开后总开关生效，推送所有新 PAYLOAD 编目</span>
          </label>
          <input v-model="form.nod_enabled" type="checkbox" />
        </div>
        <div class="row checkbox-row">
          <label>
            <span>每日摘要</span>
            <span class="hint">无新对象时也发送一条确认消息</span>
          </label>
          <input v-model="form.nod_daily_summary" type="checkbox" />
        </div>
        <label>
          <span>关注发射批次</span>
          <span class="hint">每行一个国际编号前缀（如 2026-085），命中后无论总开关状态均推送并标记"关注中"</span>
        </label>
        <textarea
          v-model="form.nod_watched_str"
          class="input"
          rows="4"
          placeholder="2026-085&#10;2026-092"
          style="resize: vertical; min-height: 80px;"
        ></textarea>
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
        <button type="submit" class="btn-primary" :disabled="saving">
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
  alerts_sgp4_reliable_floor_km: number
  alerts_only_print_on_update: boolean
  alerts_fallback_threshold: number
  xprop_enabled: boolean
  xprop_maneuver_threshold: number
  ds_fallback_threshold: number
  nod_enabled: boolean
  nod_daily_summary: boolean
  nod_watched_str: string
}

const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref("")

const form = reactive<ConfigForm>({
  norad_ids_str: "",
  alerts_reentry_warning_km: 200,
  alerts_sgp4_reliable_floor_km: 350,
  alerts_only_print_on_update: true,
  alerts_fallback_threshold: 5.0,
  xprop_enabled: true,
  xprop_maneuver_threshold: 5.0,
  ds_fallback_threshold: 3,
  nod_enabled: false,
  nod_daily_summary: false,
  nod_watched_str: "",
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
    form.alerts_sgp4_reliable_floor_km = cfg.alerts?.sgp4_reliable_floor_km ?? 350
    form.alerts_only_print_on_update = cfg.alerts?.only_print_on_update ?? true
    form.alerts_fallback_threshold = cfg.alerts?.fallback_maneuver_threshold_km ?? 5.0
    form.xprop_enabled = cfg.xpropagator?.enabled ?? true
    form.xprop_maneuver_threshold = cfg.xpropagator?.maneuver_threshold_km ?? 5.0
    form.ds_fallback_threshold = cfg.data_source?.fallback_threshold ?? 3
    const nod = cfg.new_object_discovery || {}
    form.nod_enabled = nod.enabled ?? false
    form.nod_daily_summary = nod.daily_summary ?? false
    form.nod_watched_str = (nod.watched_launches || []).join("\n")
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    error.value = `加载配置失败: ${msg}`
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
      sgp4_reliable_floor_km: form.alerts_sgp4_reliable_floor_km,
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
    new_object_discovery: {
      enabled: form.nod_enabled,
      daily_summary: form.nod_daily_summary,
      watched_launches: form.nod_watched_str
        .split(/[\n,，]+/)
        .map(s => s.trim())
        .filter(s => s.length > 0),
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
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    error.value = `保存失败: ${msg}`
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.page-desc {
  color: var(--color-text-secondary);
  margin-bottom: var(--space-xl);
  font-size: 0.9rem;
}
.settings-form {
  max-width: 640px;
}
fieldset {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 1.25rem;
  margin-bottom: 1.25rem;
  background: var(--color-surface);
}
legend {
  font-family: var(--font-heading);
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--color-signal-gold);
  padding: 0 0.5rem;
}
label {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  margin-bottom: 0.75rem;
  color: var(--color-text-primary);
  font-size: 0.9rem;
}
.hint {
  color: var(--color-text-muted);
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

/* 自定义复选框 */
input[type="checkbox"] {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border: 1px solid var(--color-border);
  border-radius: 3px;
  background: var(--color-void);
  cursor: pointer;
  position: relative;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}
input[type="checkbox"]:checked {
  background: var(--color-signal-gold);
  border-color: var(--color-signal-gold);
}
input[type="checkbox"]:checked::after {
  content: '';
  position: absolute;
  left: 5px;
  top: 2px;
  width: 5px;
  height: 9px;
  border: solid var(--color-space-black);
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

.input {
  width: 100%;
  padding: 0.45rem 0.6rem;
  background: var(--color-void);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: 0.9rem;
  outline: none;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}
.input:focus {
  border-color: var(--color-signal-gold);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.1);
}
.input-sm {
  max-width: 160px;
}

/* 只读区 */
.readonly-section legend {
  color: var(--color-text-muted);
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
  border-bottom: 1px solid rgba(30, 48, 80, 0.4);
}
.ro-key {
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  font-family: var(--font-mono);
}
.ro-reason {
  color: var(--color-text-muted);
  font-size: 0.78rem;
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  margin-top: var(--space-xl);
}
.saved-msg {
  color: var(--color-nominal-green);
  font-size: 0.85rem;
}
.error-msg {
  color: var(--color-critical-red);
  font-size: 0.85rem;
}
</style>
