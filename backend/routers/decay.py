from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.services.data_loader import load_decay_state, load_latest_satellites

router = APIRouter(prefix="/api/decay", tags=["decay"])
templates = Jinja2Templates(directory="backend/templates")


@router.get("")
async def get_decay_status():
    """
    返回每颗卫星的衰降状态。
    数据来源于 decay_state.json
    """
    state = load_decay_state()
    sats = load_latest_satellites()
    norad_names = {s.get("norad"): s.get("name", "TBA") for s in sats}

    results = []
    for norad_str, phase in state.items():
        norad_id = int(norad_str)
        results.append({
            "norad": norad_id,
            "name": norad_names.get(norad_id, "TBA"),
            "phase": phase,
        })

    # 按 norad 排序
    results.sort(key=lambda r: r["norad"])
    return {"satellites": results, "total": len(results)}


@router.get("/page", response_class=HTMLResponse)
async def decay_page(request: Request):
    """衰降状态面板页面"""
    state = load_decay_state()
    sats = load_latest_satellites()
    norad_map = {s.get("norad"): s for s in sats}

    results = []
    for norad_str, phase in state.items():
        norad_id = int(norad_str)
        sat = norad_map.get(norad_id, {})
        results.append({
            "norad": norad_id,
            "name": sat.get("name", "TBA"),
            "phase": phase,
            "periapsis": sat.get("periapsis"),
            "apoapsis": sat.get("apoapsis"),
        })

    results.sort(key=lambda r: r["norad"])
    return templates.TemplateResponse(
        request,
        "decay.html",
        {"satellites": results, "active_page": "decay"},
    )
