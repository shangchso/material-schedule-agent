"""工具三：时段查询。

查询指定发布时段是否已被占用；若被占用，返回占用方信息与下一个可用时段，
供 Agent 决定是否建议替代时段。
"""

from __future__ import annotations

from typing import Any, Dict

from ..data_store import DataStore


def query_slot(store: DataStore, slot: str) -> Dict[str, Any]:
    """查询时段占用情况。

    Args:
        store: 数据仓库。
        slot: 待查询时段，格式如 "18:00"。

    Returns:
        统一结构的工具返回结果。
    """
    if not isinstance(slot, str) or ":" not in slot:
        return {
            "ok": False,
            "tool": "slot_query",
            "arguments": {"slot": slot},
            "error": f"时段格式非法：{slot}，应为 HH:MM 形式",
        }

    occupied = store.is_slot_occupied(slot)
    result: Dict[str, Any] = {
        "slot": slot,
        "occupied": occupied,
    }

    if occupied:
        owner = store.get_slot_owner(slot)
        result["owner"] = owner
        result["next_available_slot"] = store.find_next_available_slot(after_slot=slot)
    else:
        result["next_available_slot"] = slot

    return {
        "ok": True,
        "tool": "slot_query",
        "arguments": {"slot": slot},
        "result": result,
    }
