from __future__ import annotations

from fastapi import APIRouter

from backend.services.data_loader import load_decay_state, load_latest_satellites

router = APIRouter(prefix="/api/decay", tags=["decay"])


@router.get("")
async def get_decay_status():
    """
    返回每颗卫星的衰降状态。
    数据来源于 decay_state.json
    """
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

    # 按 norad 排序
    results.sort(key=lambda r: r["norad"])
    return {"satellites": results, "total": len(results)}
