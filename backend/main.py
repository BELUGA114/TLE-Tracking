"""
TLE-Tracking Web 仪表盘 — FastAPI 应用入口

启动后端（开发）：
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

启动前端（开发）：
    cd frontend && pnpm dev

构建前端（生产）：
    cd frontend && pnpm build
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from backend.routers import config, decay, discovery, history, satellites
from backend.security import inject_cesium_token
from backend.services.ws_manager import file_watcher, manager, send_initial
from common.logging_config import setup_logging

setup_logging("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger(__name__)
    logger.info("TLE-Tracking 仪表盘已启动")
    watcher = asyncio.create_task(file_watcher())
    yield
    watcher.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watcher


app = FastAPI(
    title="TLE-Tracking 仪表盘",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(satellites.router)
app.include_router(history.router)
app.include_router(decay.router)
app.include_router(config.router)
app.include_router(discovery.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    await send_initial(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        # 非正常断开（网络重置、协议错误等）在生产中常见，用 debug 保留栈但不刷 warning
        logging.getLogger(__name__).debug("WebSocket 异常断开", exc_info=True)
        manager.disconnect(ws)


# 生产模式：提供 Vue SPA 构建产物
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    # 启动时注入 Cesium Ion token（不编译进前端构建产物，运行时由环境变量控制）
    _index_path = _frontend_dist / "index.html"
    _raw_index_html = _index_path.read_text(encoding="utf-8")
    _cesium_token = os.environ.get("CESIUM_ION_TOKEN", "")
    _index_html = inject_cesium_token(_raw_index_html, _cesium_token)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = (_frontend_dist / full_path).resolve()
        frontend_root = _frontend_dist.resolve()
        # 阻止路径穿越攻击：确保解析后的路径在 dist 目录内
        try:
            file_path.relative_to(frontend_root)
        except ValueError:
            return HTMLResponse(_index_html)
        if file_path.is_file():
            return FileResponse(file_path)
        return HTMLResponse(_index_html)
