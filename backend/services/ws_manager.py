from __future__ import annotations

import asyncio
import json
import os

from fastapi import WebSocket

from backend.services.data_loader import (
    get_data_dir,
    load_change_history,
    load_decay_state,
    load_latest_satellites,
    merge_raw_elements,
)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, message: str) -> None:
        dead: list[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.discard(ws)

    @property
    def count(self) -> int:
        return len(self.active)


manager = ConnectionManager()


def _load_satellites() -> list[dict]:
    sats = load_latest_satellites()
    merge_raw_elements(sats)
    return sats


def _load_history() -> list[dict]:
    records = load_change_history(limit=500)
    merge_raw_elements(records)
    return records


def _load_decay() -> list[dict]:
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
    return results


async def send_initial(ws: WebSocket) -> None:
    """向新连接的客户端发送全部当前数据"""
    try:
        sats = _load_satellites()
        await ws.send_text(json.dumps(
            {"type": "satellites", "data": {"satellites": sats, "total": len(sats)}},
            ensure_ascii=False,
        ))
    except Exception:
        pass

    try:
        records = _load_history()
        await ws.send_text(json.dumps(
            {"type": "history", "data": {"changes": records, "total": len(records)}},
            ensure_ascii=False,
        ))
    except Exception:
        pass

    try:
        results = _load_decay()
        await ws.send_text(json.dumps(
            {"type": "decay", "data": {"satellites": results, "total": len(results)}},
            ensure_ascii=False,
        ))
    except Exception:
        pass


async def broadcast_satellites() -> None:
    sats = _load_satellites()
    await manager.broadcast(json.dumps(
        {"type": "satellites", "data": {"satellites": sats, "total": len(sats)}},
        ensure_ascii=False,
    ))


async def broadcast_history() -> None:
    records = _load_history()
    await manager.broadcast(json.dumps(
        {"type": "history", "data": {"changes": records, "total": len(records)}},
        ensure_ascii=False,
    ))


async def broadcast_decay() -> None:
    results = _load_decay()
    await manager.broadcast(json.dumps(
        {"type": "decay", "data": {"satellites": results, "total": len(results)}},
        ensure_ascii=False,
    ))


async def file_watcher() -> None:
    """后台监听数据文件变化，有变化时广播更新"""

    data_dir = get_data_dir()
    files: dict[str, float] = {
        "tle_data.jsonl": 0,
        "decay_state.json": 0,
    }
    for name in files:
        path = os.path.join(data_dir, name)
        files[name] = os.path.getmtime(path) if os.path.exists(path) else 0

    while True:
        await asyncio.sleep(3)
        changed: list[str] = []
        for name in files:
            path = os.path.join(data_dir, name)
            mtime = os.path.getmtime(path) if os.path.exists(path) else 0
            if mtime != files[name]:
                files[name] = mtime
                changed.append(name)

        if not changed or not manager.count:
            continue

        tasks = []
        if "tle_data.jsonl" in changed:
            tasks.append(broadcast_satellites())
            tasks.append(broadcast_history())
        if "decay_state.json" in changed:
            tasks.append(broadcast_decay())
        if tasks:
            await asyncio.gather(*tasks)
