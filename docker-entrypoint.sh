#!/bin/sh
set -e

# 默认启动监控，通过 DISABLE_MONITOR=true 环境变量关闭
if [ "${DISABLE_MONITOR}" != "true" ] && [ -f /app/config.yaml ]; then
  echo "启动 TLE 数据监控..."
  python spacetrack_monitor.py &
  echo "监控进程 PID: $!"
fi

exec "$@"
