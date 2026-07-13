from __future__ import annotations

from fastapi import APIRouter

from backend.services.data_loader import load_latest_satellites, merge_raw_elements

router = APIRouter(prefix="/api/satellites", tags=["satellites"])


@router.get("")
async def get_satellites():
    """返回所有卫星的当前轨道数据（JSON）"""
    sats = load_latest_satellites()
    merge_raw_elements(sats)
    return {"satellites": sats, "total": len(sats)}


@router.get("/{norad_id}")
async def get_satellite(norad_id: int):
    """返回单颗卫星的最新轨道数据"""
    sats = load_latest_satellites()
    for sat in sats:
        if sat.get("norad") == norad_id:
            merge_raw_elements([sat])
            return sat
    return {"error": f"NORAD ID {norad_id} not found"}, 404
