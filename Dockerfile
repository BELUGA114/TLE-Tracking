# Stage 1: 构建 Vue 3 前端
# 前端产物与 CPU 架构无关，固定在 BuildKit 原生构建平台执行，避免
# linux/arm64 多架构发布时通过 QEMU 运行 Node/Vite 导致非法指令退出。
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend-builder

WORKDIR /build
COPY frontend/ .

# Docker 构建没有交互式 TTY，避免 pnpm 清理 node_modules 时等待确认。
ENV CI=true
RUN corepack enable && pnpm install --frozen-lockfile && pnpm build

# Stage 2: Python 后端 + 核心监控 + 静态文件服务
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

LABEL description="TLE-Tracking Orbital Monitor — Web Dashboard"
LABEL version="2.0"

WORKDIR /app

# 安装 Python 依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"

# 复制核心监控脚本
COPY spacetrack_monitor.py .
COPY celestrak_fetcher.py .
COPY telegram_notifier.py .
COPY new_object_watcher.py .
COPY telegram_bot.py .
COPY xpropagator_client.py .
COPY common/ common/
COPY api/ api/

# 复制后端 Web 服务
COPY backend/ backend/

# 从构建阶段复制前端构建产物
COPY --from=frontend-builder /build/dist frontend/dist/

EXPOSE 8000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--log-level", "warning"]
