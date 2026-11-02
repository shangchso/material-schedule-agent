"""工具一：素材读取。

按素材 ID 读取素材及其元数据。支持 recheck（补查）模式：
当 Agent 发现信息缺失并决定补查时，会以 recheck=True 再次调用本工具，
工具重新核对数据源后返回该字段是否可以补全。
"""

from __future__ import annotations

from typing import Any, Dict

from ..data_store import DataStore

# 元数据中必须存在的字段，缺失或为空都视为信息不完整。
REQUIRED_METADATA_FIELDS = ("title", "type", "duration_sec")


def _find_missing_fields(metadata: Dict[str, Any]) -> list[str]:
    """返回元数据中缺失或为空的字段名列表。"""
    missing: list[str] = []
    for field in REQUIRED_METADATA_FIELDS:
        if field not in metadata or metadata[field] in (None, ""):
            missing.append(field)
    return missing


def read_material(
    store: DataStore, material_id: str, recheck: bool = False
) -> Dict[str, Any]:
    """读取素材。

    Args:
        store: 数据仓库。
        material_id: 素材 ID。
        recheck: 是否为补查调用。补查时工具会重新核对缺失字段能否补全。

    Returns:
        统一结构的工具返回结果。
    """
    material = store.get_material(material_id)
    if material is None:
        return {
            "ok": False,
            "tool": "material_reader",
            "arguments": {"material_id": material_id, "recheck": recheck},
            "error": f"素材 {material_id} 不存在，无法读取",
        }

    missing_fields = _find_missing_fields(material.get("metadata", {}))

    result: Dict[str, Any] = {
        "material_id": material_id,
        "metadata": material["metadata"],
        "requested_time": material["requested_time"],
        "hard_requirement": material["hard_requirement"],
        "incomplete": bool(missing_fields),
        "missing_fields": missing_fields,
    }

    if recheck:
        # 补查：重新核对数据源。合成数据源中缺失字段无法自动补全。
        result["recheck"] = True
        if missing_fields:
            result["recheck_resolved"] = False
            result["recheck_note"] = "数据源中该字段确实缺失，无法自动补全"
        else:
            result["recheck_resolved"] = True
            result["recheck_note"] = "补查完成，字段齐全"

    return {
        "ok": True,
        "tool": "material_reader",
        "arguments": {"material_id": material_id, "recheck": recheck},
        "result": result,
    }
