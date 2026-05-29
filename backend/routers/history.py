from __future__ import annotations

from fastapi import APIRouter, Query

from backend.services.data_loader import load_change_history, load_satellite_history

router = APIRouter(prefix="/api/history", tags=["history"])


def _merge_raw(records: list[dict]) -> None:
    """将 _raw_elements 中的字段合并到顶层"""
    for r in records:
        if raw := r.pop("_raw_elements", None):
            r.update(raw)


@router.get("/changes")
async def get_changes(limit: int = Query(50, ge=1, le=500)):
    """返回最近的 TLE 变化事件"""
    records = load_change_history(limit=limit)
    _merge_raw(records)
    return {"changes": records, "total": len(records)}


@router.get("/satellite/{norad_id}")
async def get_satellite_history(
    norad_id: int,
    limit: int = Query(100, ge=1, le=1000),
):
    """返回指定卫星的 TLE 变化历史"""
    records = load_satellite_history(norad_id, limit=limit)
    _merge_raw(records)
    return {"norad_id": norad_id, "records": records, "total": len(records)}
