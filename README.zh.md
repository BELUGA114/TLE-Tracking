# TLE-Tracking

**Language / 语言**: [English](README.md) | [中文](#)

---

一个支持双数据源的轻量级轨道监控系统，带 Web 仪表盘和 Telegram Bot。

## 功能

- **TLE 监控** — 双源（Space-Track / CelesTrak）自动轮询，支持故障切换
- **变化分类** — 区分真实机动与解算修正（哈希比对 + 可选 xpropagator 残差分析）
- **新对象发现** — Space-Track SATCAT 新编目载荷检测，Telegram 推送
- **Telegram Bot** — 双向交互：开关切换、关注列表管理（命令 + 行内键盘）
- **Web 仪表盘** — Vue 3 实时展示轨道数据、趋势图表、衰降状态
- **衰降分析** — 四级衰减判定，自动分级告警
- **Docker 部署** — 多架构镜像，一键 `docker compose up -d`

## 快速开始

### 1. 安装依赖

```bash
pip install requests python-dotenv pyyaml fastapi uvicorn
```

### 2. 配置

复制 `.env.example` 为 `.env`，填写凭据（CelesTrak 主源时 Space-Track 可选）：

```env
SPACETRACK_USER=your_email@example.com
SPACETRACK_PASS=your_password
TELEGRAM_BOT_TOKEN=your_bot_token      # 新对象发现需要
TELEGRAM_CHAT_ID=your_chat_id          # 新对象发现需要
```

> **如何获取 Telegram 凭据：**
> - `TELEGRAM_BOT_TOKEN` — 向 Telegram 上的 [@BotFather](https://t.me/BotFather) 发送 `/newbot`，按提示创建机器人即可获得
> - `TELEGRAM_CHAT_ID` — 向 [@UserIDxBot](https://t.me/UserIDxBot) 发送 `/id` 即可看到你的数字 ID，或给创建好的 Bot 发条消息后访问 `https://api.telegram.org/bot{TOKEN}/getUpdates` 查看
```

编辑 `config.yaml`：

```yaml
targets:
  norad_ids: [25544, 48273]

data_source:
  primary: "celestrak"       # 主源，celestrak 无需认证
  fallback: "spacetrack"

new_object_discovery:
  enabled: true              # 开启新对象发现
  watched_launches:          # 关注列表（可选）
    - intldes_prefix: "2026-085"
      label: "星链 G12-3"
```

标记 `# web:` 的字段可在仪表盘设置页在线修改，热重载生效。

### 3. 运行

```bash
python spacetrack_monitor.py    # 监控 + 内建 Web 服务
python telegram_bot.py          # Telegram Bot（独立进程）
```

### 4. Docker

```bash
docker compose up -d            # 监控 + 仪表盘 + Bot 一键启动
```

访问 `http://localhost:8000`。Bot 凭据配置后自动启动。预构建镜像：`ghcr.io/beluga114/tle-tracking:latest`。

**代理（可选）：** 如果外部服务（Telegram、Space-Track）需要走代理，在 `.env` 中添加：

```env
HTTP_PROXY=http://host:port
HTTPS_PROXY=http://host:port
```

容器通过 `docker-compose.yml` 继承这些变量。已预设 `NO_PROXY=localhost,127.0.0.1,::1`——内部 API 调用（Bot → 仪表盘 localhost:8000）不走代理，不需要代理时留空或不设置即可

### 5. 本地开发

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000   # 后端
cd frontend && pnpm install && pnpm dev                        # 前端 (:5173)
```

## 新对象发现 & Telegram Bot

每天 UTC 17:10（SATCAT 日更后）查询 Space-Track 过去 24h 新编目的 PAYLOAD 对象，推送到 Telegram。

```
Space-Track SATCAT → new_object_watcher.py → Telegram 通知
                                              └── Web 设置页
```

**Bot 命令**：

| 命令 | 作用 |
|---|---|
| `/start` | 主菜单 |
| `/status` | 状态 + 开关 |
| `/watchlist` | 关注列表管理 |
| `/addwatch <前缀> [备注]` | 添加关注 |
| `/rmwatch <前缀>` | 移除关注 |
| `/help` | 帮助 |

关注列表支持前缀匹配（`2026-085` 命中 `2026-085A`/`2026-085B`）。命中项无论总开关状态均推送，打"关注中"标签。

## Web 仪表盘

| 页面 | 路由 | 功能 |
|---|---|---|
| 仪表盘 | `/` | 卫星表格、搜索筛选、轨道分布图 |
| TLE 变化 | `/history` | 变化时间线、参数对比 |
| 衰降状态 | `/decay` | 阶段饼图、散点图、等级列表 |
| 卫星详情 | `/satellite/{id}` | 完整参数、趋势图、历史 |
| 设置 | `/settings` | 在线修改配置，热重载 |

技术栈：Vue 3 + FastAPI + WebSocket + ECharts + CesiumJS

## 配置参考

```yaml
# HTTP 请求头 User-Agent，可选，留空则不发送
user_agent: ''

targets:
  norad_ids: [25544]          # web: 监控的卫星 NORAD ID 列表，可多个

schedule:
  minute: 17                  # Space-Track 每小时第几分请求（避开 :00/:30 高峰）

files:
  data_dir: /data             # 数据文件目录，Docker 建议 /data，Windows 默认项目目录
  data_file: tle_data.jsonl   # 轨道数据文件名
  cache: tle_cache.json       # 断点恢复缓存文件名
  run_log: tle_log.jsonl      # 运行日志文件名
  max_log_size_mb: 10         # 日志文件超过此大小自动轮转（MB）

alerts:
  reentry_warning_km: 200             # web: 近地点低于此值触发再入预警
  only_print_on_update: true          # web: 仅在 TLE 变化时打印，关闭可看每次查询结果
  fallback_maneuver_threshold_km: 5.0 # web: xpropagator 不可用时，近/远地点变化超过此值视为机动

retry:
  login_max_failures: 5       # Space-Track 登录连续失败 N 次后放弃本轮
  login_pause_seconds: 1800   # 登录失败后等待时间（秒）
  request_max_retries: 3      # HTTP 请求失败最大重试次数
  request_retry_base: 5       # 指数退避基数（秒），第 N 次重试等待 base × 2^(N-1)

xpropagator:
  enabled: true               # web: 启用高精度残差分析（需自行部署 xpropagator 服务）
  host: localhost             # gRPC 服务地址
  port: 50051                 # gRPC 服务端口
  maneuver_threshold_km: 5.0  # web: 残差超过此值判定为真实机动（km）

data_source:
  primary: celestrak          # 主数据源（celestrak / spacetrack）
  fallback: spacetrack        # 备数据源（spacetrack / none）——主源故障时自动切换
  fallback_threshold: 3       # web: 主源连续失败 N 次后切换备源
  celestrak_interval_seconds: 7200    # CelesTrak 轮询间隔（秒），API 合规要求 >= 7200
  use_supplemental: false     # 是否使用 CelesTrak 补充数据（sup-gp）

new_object_discovery:
  enabled: false              # web: 启用新 PAYLOAD 编目发现（需 Telegram 凭据）
  schedule_hour: 17           # 每天几点检查（UTC），默认 17:00 SATCAT 更新后
  schedule_minute: 10         # 几点几分，留 10 分钟给 SATCAT 刷新
  backtrack_hours: 72         # 宕机恢复窗口（小时），超过此时间仅发摘要不逐条推送
  daily_summary: false        # web: 无新对象时也发一条 "今日无新" 的每日确认
  watched_launches: []        # web: 关注发射批次列表，命中后无论总开关均推送
                              # 每项格式: intldes_prefix (必填) + label (可选)
                              # 示例:
                              #   - intldes_prefix: "2026-085"
                              #     label: "星链G12"
                              #   - intldes_prefix: "2026-092"
```

标记 `# web` 的字段可在 `/settings` 页面在线修改，下一轮询周期生效。

## 数据文件

运行后自动生成于 `DATA_DIR`：

> **优先级**：`DATA_DIR` 环境变量 > `config.yaml` `files.data_dir` > 平台默认。
> Docker：`/data`（挂载宿主机 `./data`）。Windows：项目目录。

- `tle_data.jsonl` — 核心轨道数据，含 `change_type`（initial/correction/maneuver/decaying）
- `tle_cache.json` — 断点恢复缓存
- `tle_log.jsonl` — 运行日志
- `new_object_cursor.json` — 新对象发现游标

日志超过 10MB 自动轮转。

## 关于再入预测

基于 BSTAR 的简化大气模型，极其粗略，仅供娱乐。忽略姿态、太阳活动、空间天气等因素——误差可达数倍。如需严肃分析，请使用专业轨道传播器（SGP4/SGP4-XP）配合高精度大气模型。

## 轨道预报 (xpropagator)

可选高精度残差分析：将旧 TLE 传播到新历元，计算 ECI 位置差。

- 残差 >= 阈值 → 真实机动
- 残差 < 阈值 → 解算修正

需要自行部署 [xpropagator](https://github.com/xpropagation/xpropagator) 服务，本项目不含 SGP4 二进制文件。

## 速率限制

- **Space-Track**：gp 端点 1 次/小时，satcat_debut 1 次/天。违规封号
- **CelesTrak**：每星 2 小时 1 次

避开 :00/:30 整半点高峰。**请勿修改调度逻辑规避限制**。

## 相关链接

- [Space-Track.org](https://www.space-track.org/)
- [CelesTrak.org](https://celestrak.org/)
- [xpropagator](https://github.com/xpropagation/xpropagator)
