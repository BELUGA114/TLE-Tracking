#!/bin/sh
set -e

# 默认启动监控，通过 DISABLE_MONITOR=true 环境变量关闭
if [ "${DISABLE_MONITOR}" != "true" ] && [ -f /app/config.yaml ]; then
  echo "启动 TLE 数据监控..."
  python spacetrack_monitor.py &
  echo "监控进程 PID: $!"
fi

# 启动 Telegram Bot（凭据存在就启动，与 enabled 状态无关——bot 的 /enable 命令就是用来开的）
if [ -n "${TELEGRAM_BOT_TOKEN}" ] && [ -n "${TELEGRAM_CHAT_ID}" ]; then
  echo "启动 Telegram Bot 轮询..."
  python telegram_bot.py &
  echo "Telegram Bot 进程 PID: $!"
fi

exec "$@"
