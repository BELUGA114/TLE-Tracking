# TLE-Tracking

**Language / 语言**: [English](README.md) | [中文](#)

---

一个支持双数据源（Space-Track.org 和 CelesTrak）的轻量级轨道监控系统，提供简单的 Web 仪表盘实时展示轨道数据。

**核心能力**：

- **数据采集** — 自动监控单颗或多颗卫星的 TLE 更新，支持双源故障转移
- **变化分类** — 自动分辨解算修正与真实机动（哈希比对 + 可选 xpropagator 残差分析）
- **Web 仪表盘** — 实时展示轨道数据、趋势图表、衰降状态
- **实时推送** — WebSocket 实时推送，页面自动响应数据更新
- **衰降分析** — 自动检测轨道衰降趋势并分级告警
- **Docker 一键部署** — 监控 + 仪表盘

---

## 特性
- 智能调度系统：同时考虑调度时刻和速率限制
- TLE 变化分类：区分解算修正（Correction）与真实机动（Maneuver）
  - 默认使用简单的近地点/远地点阈值规则
  - 可选启用高精度残差分析（依靠 xpropagator 服务）
- 断点恢复机制：程序崩溃后自动从缓存恢复未处理数据
- 重启自动恢复状态：从历史数据恢复上次轨道状态

## 快速开始

### 1. 安装 Python 依赖

确保你已经安装了 Python，然后在项目目录下运行：

```bash
pip install requests python-dotenv pyyaml
```

---

### 2. 配置凭据

**步骤 1：复制模板文件**

将 `.env.example` 复制一份并重命名为 `.env`：

```bash
cp .env.example .env
```

**步骤 2：填写凭据（Space-Track 模式必需）**

用文本编辑器打开 `.env` 文件，填入你的 Space-Track 账号和密码：

```env
SPACETRACK_USER=your_email@example.com
SPACETRACK_PASS=your_password
```

> - `.env` 文件包含你的账号密码，不要分享给他人
> - 如果没有 Space-Track 账号，需要先去 [space-track.org](https://www.space-track.org) 注册
> - **注意**：如果使用 CelesTrak 作为主数据源，Space-Track 凭据为可选

---

### 3. 配置监控目标与数据源

编辑 `config.yaml` 文件以修改监控的卫星或调整其他参数。

**最简单的用法**：使用默认配置监控 ISS（CelesTrak 作为主数据源，无需认证）

**自定义配置示例**：

```yaml
targets:
  norad_ids: [25544, 48273]  # 监控多个卫星

schedule:
  minute: 17  # 每小时第 17 分钟请求数据（仅 Space-Track 模式）

data_source:
  primary: "celestrak"         # 主数据源: "celestrak" | "spacetrack"
  fallback: "spacetrack"       # 备源
  fallback_threshold: 3        # 主源连续失败几次后切换备源
```

> **提示**：修改 `config.yaml` 后需要重启脚本才能生效

---

### 4. （可选）配置 xpropagator 残差分析

```bash
pip install grpcio grpcio-tools
```

在 `config.yaml` 中启用 `xpropagator` 配置段，然后参见下方的 [轨道预报后端 (xpropagator)](#轨道预报后端-xpropagator) 章节。

---

### 5. 运行脚本

在项目目录下运行：

```bash
python spacetrack_monitor.py
```

首次运行时，脚本会：
1. 加载你的配置
2. 如需冷启动（为新卫星从 CelesTrak 获取初始数据）
3. 立即执行第一次数据拉取
4. 之后按配置的调度自动检查

看到类似以下输出表示运行成功：

```
2026-05-02 10:00:00 TLE-Tracking 轨道监控  主源: celestrak  备源: spacetrack
2026-05-02 10:00:00 目标: 25544
2026-05-02 10:00:00 调度: 每 2 小时 (CelesTrak) | 再入预警: <200 km
```

---

### 6. Docker 部署

使用 Docker Compose 一键部署监控 + Web 仪表盘（多阶段构建，自动编译前端）：

```bash
# 构建并启动（监控 + Web 仪表盘）
docker compose up -d

# 查看日志
docker compose logs -f

# 仅启动 Web 仪表盘（不启动数据采集）
DISABLE_MONITOR=true docker compose up -d

# 停止
docker compose down
```

启动后访问 **http://localhost:8000** 即可打开仪表盘。

**宿主机文件布局**：
```
project/
├── config.yaml      # 配置文件（挂载）
├── .env             # 凭据文件（可选）
└── data/            # 运行数据（持久化卷）
    ├── tle_data.jsonl
    ├── tle_log.jsonl
    ├── tle_cache.json
    ├── decay_state.json
    └── celestrak_poll_cache.json
```

> 修改宿主机 `config.yaml` 后重启容器即可生效：`docker compose restart`，无需重建镜像。

### 7. 本地开发（无 Docker）

**启动后端**：

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**启动前端**（需先安装 Node.js 22+ 和 pnpm）：

```bash
cd frontend
pnpm install
pnpm dev
```

前端开发服务器运行在 `http://localhost:5173`，API 请求自动代理到后端 8000 端口。

---

## Web 仪表盘

基于 **Vue 3 + FastAPI + WebSocket** 的 Web 仪表盘，将轨道数据以图表和表格形式可视化，支持实时推送更新

| 页面 | 路线 | 功能 |
|---|---|---|
| **仪表盘** | `/` | 卫星总览表格、搜索筛选、轨道高度分布图、可展开详细参数 |
| **TLE 变化** | `/history` | TLE 更新时间线，可展开对比参数差异 |
| **衰降状态** | `/decay` | 衰降阶段饼图、近地点/远地点散点图、等级列表 |
| **卫星详情** | `/satellite/{noradId}` | 完整轨道参数、近地点/远地点趋势图、历史记录 |

**架构**:
```
spacetrack_monitor.py → data/*.jsonl → FastAPI 文件监听 → WebSocket → Vue 3 SPA (ECharts)
```

---

### 业务配置

所有配置通过 `config.yaml` 完成。文件中有完整的参数说明和注释，直接编辑即可。修改后重启脚本生效

### 数据文件

脚本运行后会自动生成以下文件：

- **tle_data.jsonl**: 核心轨道数据（每次 TLE 更新时记录），每条记录包含 `change_type` 字段（initial/correction/maneuver），便于后处理过滤真实机动事件，带轮转保护
- **tle_cache.json**: 临时缓存，保存上次请求时间、全量原始数据和待处理标记，支持断点恢复，自动覆盖
- **tle_log.jsonl**: 运行日志，记录程序运行状态，带轮转保护

> **日志轮转**：当文件大小超过配置的阈值（默认 10MB）时，会自动重命名为 `.bak` 备份文件。

> **跨平台数据目录说明**：
> - **Linux / Docker**：默认为 `/data`（通过 `config.yaml` 的 `files.data_dir` 配置）。Docker 中请确保 volume 挂载到 `/data` 以实现持久化。
> - **Windows**：默认为项目当前目录（`.`）。可通过 `DATA_DIR` 环境变量覆盖，或修改 `config.yaml` 中的 `data_dir` 配置。
> - **覆盖优先级**：`DATA_DIR` 环境变量 > `config.yaml` 的 `files.data_dir` > 平台默认值。

---

## 输出示例

### 控制台输出

```text
2026-04-27 14:12:01 [25544] 本批次共 3 条解算记录，取最新一条
2026-04-27 14:12:01 [25544] 检测到 TLE 变化！(hash: abc123 → def456, 类型: 解算修正 (Correction))

  ===============================================
    ISS (ZARYA)          NORAD 25544
    国际编号: 1998-067A
    历元:     2026-04-27T14:08:32
    近地点:   418.5 km    远地点: 421.2 km
    倾角:     51.6400°   周期: 92.870 min
    离心率:   0.0002000   BSTAR: 2.3456e-04
    TLE Hash: abcdef1234567890
  ===============================================  （近地点 +0.3 km，远地点 +0.2 km）
  1 25544U 98067A   ...
  2 25544  51.6400 ...
```

### 看起来反常的等待提示？（其实是预期行为）

示例：
```text
2026-04-25 00:30:13 下次查询：02:12 UTC（102 分钟后）
```

**为什么会出现 "102 分钟"？** 脚本严格遵守两条规则：避开整点和半点高峰期（:00、:30），且两次请求间隔至少 60 分钟。当约束条件将下次可用时间推到调度时刻之后时，会自动顺延到下一个调度小时——所以看起来等待时间很长。这是预期行为，用于确保 API 合规、账号安全和长期稳定运行。

---

## 轨道预报后端 (xpropagator)

### 重要声明

**本仓库不包含或分发 USSF SGP4/SGP4-XP 二进制文件。** TLE-Tracking 仅通过网络 gRPC 调用外部 xpropagator 服务。部署说明请参考 [xpropagator 官方仓库](https://github.com/xpropagation/xpropagator)。

> 本仓库的 MIT 许可证仅适用于 TLE-Tracking 自有代码，外部组件和服务遵循其各自的许可条款。

### 残差分析原理

当检测到 TLE 更新时：

1. **旧 TLE 向前传播**：将旧 TLE 传播到新 TLE 的历元时刻
2. **新 TLE 初始化**：在新历元时刻初始化新 TLE
3. **计算残差**：在 ECI 笛卡尔坐标系中计算位置差（km）
4. **判定规则**：
   - 残差 >= 机动判定阈值 → 真实机动（Maneuver）
   - 残差 < 机动判定阈值 → 解算修正（Correction）

这种方法比直接比较轨道根数更准确，因为基于 USSF 官方 SGP4-XP 模型，
在状态空间比较，消除了轨道根数解算的舍入误差。

---

## 关于再入预测

本项目中的再入时间估算极其粗糙，仅供娱乐参考。

当前实现：

- 使用 BSTAR + 简化指数大气模型
- 通过轨道平均运动变化率进行估算
- 忽略了大量关键因素（姿态、太阳活动、空间天气等）

实际误差可能达到数倍甚至更大，不适用于任何严肃分析或决策。

如需更专业的衰减预报，推荐使用专业轨道传播器（如 SGP4/SGP4-XP）和高精度大气模型（如 NRLMSISE-00）。

---

## 数据格式（JSONL）

轨道数据以 JSON lines 格式存储在 `tle_data.jsonl` 中。每条记录包含：`timestamp`、`change_type`、`norad`、`name`、`periapsis`、`apoapsis`、`epoch`、`tle_hash` 和原始 TLE 行。

**change_type 字段说明：**
- `initial` — 首次记录
- `correction` — 解算修正（近地点/远地点变化 < 阈值）
- `maneuver` — 真实机动（近地点/远地点变化 > 阈值）

阈值可通过 `alerts.fallback_maneuver_threshold_km` 配置（默认 5.0 km）。

---

## 注意事项

本项目严格遵守 Space-Track.org 和 CelesTrak.org 的 API 使用规范。

### 速率限制

- **Space-Track**：每小时仅允许向 gp 类端点发起 1 次请求，违规会导致账号被封
- **CelesTrak**：每颗卫星每 2 小时至多查询一次，过度请求可能触发临时封锁

### 推荐的查询方式

**Space-Track** — 使用批量查询获取过去一小时内发布的所有 TLE，然后在本地筛选目标卫星（详见 [Space-Track API 文档](https://www.space-track.org/documentation#/api)）。

**CelesTrak** — 按 NORAD ID 单星查询，例如 `https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=json`。

### 调度时间要求

- **Space-Track**：避开整点和半点高峰期（:00、:30），建议使用非高峰时段（如 :12、:48）
- **CelesTrak**：每 2 小时轮询一次，脚本自动控制频率

### 请勿修改调度逻辑以规避速率限制

---

## 相关链接

- [Space-Track.org](https://www.space-track.org/)
- [CelesTrak.org](https://celestrak.org/)
- [Space-Track API Documentation](https://www.space-track.org/documentation#/api)
- [xpropagator](https://github.com/xpropagation/xpropagator)
