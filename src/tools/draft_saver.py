"""工具四：排期草稿保存。

仅保存草稿，不执行任何真实发布。保存动作具备幂等性：
同一素材重复提交只保留一份草稿。通过 store.save_failure 开关
可模拟保存失败，此时必须如实返回 ok=False，不得虚报成功。
"""

from __future__ import annotations

from typing import Any, Dict

from ..data_store import DataStore


def save_draft(
    store: DataStore,
    material_id: str,
    scheduled_slot: str,
    review_status: str,
    risk_reasons: list[str],
    pending_confirmations: list[str],
    alternative_slot: bool = False,
) -> Dict[str, Any]:
    """保存排期草稿。

    Args:
        store: 数据仓库。
        material_id: 素材 ID。
        scheduled_slot: 最终排期时段。
        review_status: 审核状态（如 approved / blocked / pending_confirmation）。
        risk_reasons: 风险原因列表。
        pending_confirmations: 待用户确认项列表。
        alternative_slot: 该时段是否为替代时段。

    Returns:
        统一结构的工具返回结果。
    """
    draft = {
        "material_id": material_id,
        "scheduled_slot": scheduled_slot,
        "review_status": review_status,
        "risk_reasons": risk_reasons,
        "pending_confirmations": pending_confirmations,
        "is_alternative_slot": alternative_slot,
        "published": False,  # 永远只是草稿，不存在已发布状态。
    }

    save_result = store.save_draft(draft)

    if not save_result["ok"]:
        return {
            "ok": False,
            "tool": "draft_saver",
            "arguments": {"material_id": material_id, "scheduled_slot": scheduled_slot},
            "error": save_result["error"],
        }

    return {
        "ok": True,
        "tool": "draft_saver",
        "arguments": {"material_id": material_id, "scheduled_slot": scheduled_slot},
        "result": save_result,
    }
