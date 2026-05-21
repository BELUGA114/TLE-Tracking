FROM python:3.11-slim

LABEL description="TEL-Tracking Orbital Monitor"
LABEL version="1.0"

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 仅复制代码，不含 config.yaml / .env / 数据文件
COPY spacetrack_monitor.py .
COPY decay_tracker.py .
COPY celestrak_fetcher.py .
COPY xpropagator_client.py .
COPY api/ api/

# 数据目录卷（挂载宿主目录到 /data 实现持久化 + 配置分离）
VOLUME /data

CMD ["python", "spacetrack_monitor.py"]
