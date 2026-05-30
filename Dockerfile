# Stage 1: 构建 Vue 3 前端
FROM node:22-alpine AS frontend-builder

WORKDIR /build
COPY frontend/ .
RUN npm install && npx vite build

# Stage 2: Python 后端 + 核心监控 + 静态文件服务
FROM python:3.11-slim

LABEL description="TLE-Tracking Orbital Monitor — Web Dashboard"
LABEL version="2.0"

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制核心监控脚本
COPY spacetrack_monitor.py .
COPY celestrak_fetcher.py .
COPY xpropagator_client.py .
COPY api/ api/

# 复制后端 Web 服务
COPY backend/ backend/

# 从构建阶段复制前端构建产物
COPY --from=frontend-builder /build/dist frontend/dist/

EXPOSE 8000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
