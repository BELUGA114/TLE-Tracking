from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.services.data_loader import load_change_history, load_satellite_history

router = APIRouter(prefix="/api/history", tags=["history"])
templates = Jinja2Templates(directory="backend/templates")


@router.get("/changes")
async def get_changes(limit: int = Query(50, ge=1, le=500)):
    """返回最近的 TLE 变化事件"""
    records = load_change_history(limit=limit)
    for r in records:
        r.pop("_raw_elements", None)
        r.pop("tle1", None)
        r.pop("tle2", None)
    return {"changes": records, "total": len(records)}


@router.get("/satellite/{norad_id}")
async def get_satellite_history(
    norad_id: int,
    limit: int = Query(100, ge=1, le=1000),
):
    """返回指定卫星的 TLE 变化历史"""
    records = load_satellite_history(norad_id, limit=limit)
    for r in records:
        r.pop("_raw_elements", None)
        r.pop("tle1", None)
        r.pop("tle2", None)
    return {"norad_id": norad_id, "records": records, "total": len(records)}


@router.get("/page", response_class=HTMLResponse)
async def history_page(request: Request):
    """TLE 变化历史页面"""
    records = load_change_history(limit=100)
    for r in records:
        r.pop("_raw_elements", None)
        r.pop("tle1", None)
        r.pop("tle2", None)
    return templates.TemplateResponse(
        request,
        "history.html",
        {"records": records},
    )
