"""工具二：规则检查。

依据审核规则对素材进行检查，区分两类结果：
- missing_fields: 信息缺失（字段为空），应由 Agent 先发起补查。
- violations: 明确违反审核规则，阻断排期。
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..data_store import DataStore


def check_rules(store: DataStore, material: Dict[str, Any]) -> Dict[str, Any]:
    """对素材执行全部审核规则检查。

    Args:
        store: 数据仓库。
        material: material_reader 返回的素材数据（result 部分）。

    Returns:
        统一结构的工具返回结果，result 中含 missing_fields 与 violations。
    """
    rules = store.get_rules()
    metadata = material.get("metadata", {})
    violations: List[Dict[str, str]] = []

    # R01 标题必填
    title = metadata.get("title")
    if title is None or title == "":
        violations.append({"rule_id": "R01", "reason": "素材标题为空，不满足标题必填规则"})

    # R02 类型白名单
    allowed_types: List[str] = []
    for rule in rules:
        if rule["rule_id"] == "R02":
            allowed_types = rule["allowed_types"]
    material_type = metadata.get("type")
    if material_type and material_type not in allowed_types:
        violations.append(
            {
                "rule_id": "R02",
                "reason": f"素材类型 {material_type} 不在允许类型 {allowed_types} 内",
            }
        )

    # R03 视频时长上限
    max_duration = 0
    for rule in rules:
        if rule["rule_id"] == "R03":
            max_duration = rule["max_duration_sec"]
    duration = metadata.get("duration_sec")
    if material_type == "video" and isinstance(duration, int) and duration > max_duration:
        violations.append(
            {
                "rule_id": "R03",
                "reason": f"视频时长 {duration} 秒超过上限 {max_duration} 秒",
            }
        )

    passed = len(violations) == 0
    return {
        "ok": True,
        "tool": "rule_checker",
        "arguments": {"material_id": material.get("material_id")},
        "result": {
            "passed": passed,
            "violations": violations,
            "checked_rule_count": len(rules),
        },
    }
