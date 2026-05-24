from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.services.data_loader import load_latest_satellites

router = APIRouter(prefix="/api/satellites", tags=["satellites"])
templates = Jinja2Templates(directory="backend/templates")


@router.get("")
async def get_satellites():
    """返回所有卫星的当前轨道数据（JSON）"""
    sats = load_latest_satellites()
    for sat in sats:
        # 移除冗余的原始根数
        sat.pop("_raw_elements", None)
        sat.pop("tle1", None)
        sat.pop("tle2", None)
    return {"satellites": sats, "total": len(sats)}


@router.get("/{norad_id}")
async def get_satellite(norad_id: int):
    """返回单颗卫星的最新轨道数据"""
    sats = load_latest_satellites()
    for sat in sats:
        if sat.get("norad") == norad_id:
            sat.pop("_raw_elements", None)
            sat.pop("tle1", None)
            sat.pop("tle2", None)
            return sat
    return {"error": f"NORAD ID {norad_id} not found"}, 404


@router.get("/page", response_class=HTMLResponse)
async def satellites_page(request: Request):
    """卫星总览页面"""
    sats = load_latest_satellites()
    for sat in sats:
        sat.pop("_raw_elements", None)
        sat.pop("tle1", None)
        sat.pop("tle2", None)
    return templates.TemplateResponse(
        request,
        "satellites.html",
        {"satellites": sats, "total": len(sats)},
    )
