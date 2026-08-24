# TLE-Tracking

语言：[English](README.en.md) | 中文

轻量级轨道监控系统，跟踪卫星 TLE 更新，识别轨道变化并分析衰减趋势。支持 Space-Track 和 CelesTrak 数据源故障切换，提供 Web 仪表盘与 Telegram Bot

## 功能

- 双源 TLE 轮询和故障切换
- 基于哈希与可选 xpropagator 残差分析的变化分类
- Space-Track SATCAT 新编目 PAYLOAD 检测与 Telegram 通知
- Telegram Bot 关注列表和开关控制
- Vue 3 仪表盘、CesiumJS 三维视图和趋势图表
- 四级衰减状态判定

## 快速开始

### 配置

复制 `.env.example` 为 `.env`。使用 Space-Track 数据源时填写账号；启用新对象通知时填写 Telegram 凭据；生产环境必须设置 `DASHBOARD_API_KEY`

```env
SPACETRACK_USER=your_email@example.com
SPACETRACK_PASS=your_password
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
DASHBOARD_API_KEY=long_random_value
```

可用下列命令生成 `DASHBOARD_API_KEY`：

```bash
node -e "console.log(require('node:crypto').randomBytes(32).toString('base64url'))"
```

`CESIUM_ION_TOKEN` 可选。它会发送到浏览器，请在 Cesium Ion 中限制允许的域名和资产；未设置时前端使用 OpenStreetMap 底图

编辑 `config.yaml`，指定卫星和数据源：

```yaml
targets:
  norad_ids: [25544, 48273]

data_source:
  primary: celestrak
  fallback: none

new_object_discovery:
  enabled: true
  watched_launches:
    - intldes_prefix: 2026-085
      label: 星链 G12-3
```

### 本地部署

需要 Python 3.11+、uv、Node.js 22+ 和 pnpm（pnpm 可通过 Corepack 启用）

```bash
uv sync
corepack enable
cd frontend
pnpm install
pnpm build
cd ..
```

在独立终端中启动服务：

```bash
uv run python spacetrack_monitor.py
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
uv run python telegram_bot.py  # 配置 Telegram 凭据时可选
```

访问 `http://localhost:8000`

### 测试

```bash
uv sync --extra dev
uv run pytest
```

`scripts/` 下的集成测试脚本需外部服务：

```bash
uv run python scripts/test_telegram_bot.py   # 需 uvicorn 运行在 localhost:8000
uv run python scripts/test_xpropagator.py    # 需 xpropagator gRPC 容器运行
```

### Docker 部署

需要 Docker Engine 和 Docker Compose v2。Docker 使用当前目录的 `.env`、`config.yaml` 和 `./data` 数据卷

```bash
# 本地构建
docker compose up -d --build

# 或拉取预构建镜像
docker compose pull
docker compose up -d --no-build
```

预构建镜像为 `ghcr.io/beluga114/tle-tracking:latest`。容器启动监控器和仪表盘，配置 Telegram 凭据后也会启动 Bot。外部服务需要代理时，在 `.env` 设置 `HTTP_PROXY` 和 `HTTPS_PROXY`；容器内的 localhost API 调用不走代理

### 前端开发

```bash
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
cd frontend && pnpm install && pnpm dev
```

前端开发服务器监听 `http://localhost:5173`

## 新对象发现和 Telegram Bot

`new_object_discovery.enabled: true` 会推送全部新编目 PAYLOAD。`watched_launches` 使用国际编号前缀匹配，命中项始终推送，不受总开关影响。例如 `2026-085` 会匹配 `2026-085A` 和 `2026-085B`

| 命令 | 作用 |
| --- | --- |
| `/start` | 主菜单 |
| `/status` | 查看状态和开关 |
| `/watchlist` | 管理关注列表 |
| `/addwatch <前缀> [备注]` | 添加关注 |
| `/rmwatch <前缀>` | 移除关注 |
| `/help` | 帮助 |

## 配置参考

```yaml
# HTTP 请求头 User-Agent，可选，留空则不发送
user_agent: ''

targets:
  norad_ids: [25544]          # web: 监控的卫星 NORAD ID 列表，可多个

schedule:
  minute: 17                  # Space-Track 每小时请求分钟，避开 :00 和 :30

files:
  data_dir: /data             # 数据目录，Docker 建议 /data
  data_file: tle_data.jsonl   # 轨道数据文件名
  cache: tle_cache.json       # 断点恢复缓存文件名
  run_log: tle_log.jsonl      # 运行日志文件名
  max_log_size_mb: 10         # 日志轮转阈值，MB

alerts:
  reentry_warning_km: 200             # web: 近地点低于此值触发再入预警
  sgp4_reliable_floor_km: 350         # 低于此高度不使用 SGP4 残差分析
  only_print_on_update: true          # web: 仅在 TLE 变化时打印
  fallback_maneuver_threshold_km: 5.0 # web: xpropagator 不可用时的机动阈值，km

retry:
  login_max_failures: 5       # Space-Track 登录连续失败上限
  login_pause_seconds: 1800   # 登录失败后的等待时间，秒
  request_max_retries: 3      # HTTP 请求最大重试次数
  request_retry_base: 5       # 指数退避基数，秒

xpropagator:
  enabled: true               # web: 启用高精度残差分析，需单独部署服务
  host: localhost             # gRPC 服务地址
  port: 50051                 # gRPC 服务端口
  maneuver_threshold_km: 5.0  # web: 残差达到此值判定为机动，km

data_source:
  primary: celestrak          # 主源，celestrak 或 spacetrack
  fallback: spacetrack        # 备源，spacetrack 或 none
  fallback_threshold: 3       # web: 主源连续失败次数达到此值后切换
  celestrak_interval_seconds: 7200  # CelesTrak 单星轮询间隔，至少 7200 秒
  use_supplemental: false     # 使用 CelesTrak 补充数据 sup-gp

new_object_discovery:
  enabled: false              # web: 启用新 PAYLOAD 发现，需要 Telegram 凭据
  schedule_hour: 17           # 每日检查小时，UTC
  schedule_minute: 10         # 检查分钟，为 SATCAT 刷新预留 10 分钟
  backtrack_hours: 72         # 宕机恢复窗口，小时
  daily_summary: false        # 无新对象时发送每日确认
  watched_launches: []        # web: 优先关注列表，格式为 intldes_prefix 和可选 label
```

带 `# web` 的字段可以在 `/settings` 页面修改，下一轮询周期生效

## 运行说明

数据目录优先级为 `DATA_DIR` 环境变量 > `config.yaml` 的 `files.data_dir` > 平台默认目录。Docker 默认使用 `/data`，并挂载宿主机 `./data`

xpropagator 会将旧 TLE 传播到新历元，按 ECI 位置残差分类：残差达到阈值为机动，否则为解算修正。它需要单独部署 [xpropagator](https://github.com/xpropagation/xpropagator) 服务；高度低于 `sgp4_reliable_floor_km` 时不使用该残差分析

再入预测基于 BSTAR 简化大气模型，忽略姿态、太阳活动和空间天气，只适合作为粗略提示

请遵守数据源限制：Space-Track 的 gp 端点每小时一次、satcat_debut 每天一次；CelesTrak 每颗卫星至少间隔两小时。调度应避开每小时的 :00 和 :30

## 链接

- [Space-Track](https://www.space-track.org/)
- [CelesTrak](https://celestrak.org/)
- [xpropagator](https://github.com/xpropagation/xpropagator)
