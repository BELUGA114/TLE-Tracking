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
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import decay, history, satellites
from backend.services.ws_manager import manager, file_watcher, send_initial

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger(__name__)
    logger.info("TLE-Tracking 仪表盘已启动")
    watcher = asyncio.create_task(file_watcher())
    yield
    watcher.cancel()
    try:
        await watcher
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="TLE-Tracking 仪表盘",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(satellites.router)
app.include_router(history.router)
app.include_router(decay.router)


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
        manager.disconnect(ws)


# 生产模式：提供 Vue SPA 构建产物
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "health":
            return {"error": "not found"}, 404
        # 尝试返回 dist 中的静态文件
        file_path = _frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # SPA 回退
        return FileResponse(_frontend_dist / "index.html", media_type="text/html")
