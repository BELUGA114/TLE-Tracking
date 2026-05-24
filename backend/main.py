"""
TLE-Tracking Web 仪表盘 — FastAPI 应用入口

启动：
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.routers import decay, history, satellites
from backend.services.data_loader import load_change_history, load_latest_satellites

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

templates = Jinja2Templates(directory="backend/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger(__name__).info("TLE-Tracking 仪表盘已启动")
    yield


app = FastAPI(
    title="TLE-Tracking 仪表盘",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(satellites.router)
app.include_router(history.router)
app.include_router(decay.router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """仪表盘首页"""
    sats = load_latest_satellites()
    records = load_change_history(limit=5)
    total_records = 0
    data_file = None
    for p in ["data/tle_data.jsonl", "tle_data.jsonl"]:
        import os as _os
        if _os.path.exists(p):
            data_file = p
            break
    if data_file:
        try:
            with open(data_file, "r") as f:
                total_records = sum(1 for _ in f)
        except Exception:
            pass

    for sat in sats:
        sat.pop("_raw_elements", None)
        sat.pop("tle1", None)
        sat.pop("tle2", None)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "satellites": sats,
            "records": records,
            "total_records": total_records,
            "active_page": "dashboard",
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
