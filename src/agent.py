"""Agent 核心：ReAct 决策循环。

循环结构（笔试硬性要求）：
    模型选择动作 → 执行工具 → 观察结果 → 模型调整下一步或结束

保护机制：
- max_steps 限制执行步数与工具调用次数，达到上限时返回明确的未完成状态。
- 所有工具调用与决策依据写入 Trace，供评审核对动态决策过程。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import tools
from .data_store import DataStore
from .llm import MockLLM


def _initial_state(material_id: str, user_confirmed: bool) -> Dict[str, Any]:
    """构建 Agent 初始状态。"""
    return {
        "material_id": material_id,
        "material": None,
        "read_error": None,
        "recheck_done": False,
        "recheck_resolved": False,
        "rule_checked": False,
        "rule_passed": False,
        "violations": [],
        "slot_checked": False,
        "requested_slot_occupied": False,
        "current_slot": None,
        "last_next_available": None,
        "alternative_query_done": False,
        "alternative_slot": None,
        "user_confirmed": user_confirmed,
        "save_done": False,
        "save_ok": False,
        "save_error": None,
        "duplicated": False,
    }


def _summarize(tool_response: Dict[str, Any]) -> str:
    """把工具完整返回压缩为简短观察摘要，写入 Trace。"""
    tool_name = tool_response.get("tool", "terminal")
    if not tool_response.get("ok", True):
        return f"{tool_name} 返回失败：{tool_response.get('error')}"
    result = tool_response.get("result")
    if result is None:
        return f"{tool_name} 执行完成"
    # 只保留关键字段，避免 Trace 过长
    keys = (
        "incomplete",
        "missing_fields",
        "recheck_resolved",
        "passed",
        "violations",
        "occupied",
        "next_available_slot",
        "duplicated",
        "message",
    )
    summary = {key: result[key] for key in keys if key in result}
    if "slot" in result:
        summary["slot"] = result["slot"]
    return f"{tool_name} 返回：{summary}"


class SchedulingAgent:
    """素材审核与发布排期 Agent。"""

    def __init__(
        self,
        store: DataStore,
        llm: Optional[Any] = None,
        llm_name: str = "MockLLM",
        max_steps: int = 8,
        user_confirmed: bool = False,
    ) -> None:
        self.store = store
        self.llm = llm or MockLLM()
        self.llm_name = llm_name
        self.max_steps = max_steps
        self.user_confirmed = user_confirmed

    def run(self, material_id: str) -> Dict[str, Any]:
        """对单个素材执行完整 ReAct 循环。

        Returns:
            最终交付结果，含审核状态、风险原因、建议时段、待确认项、
            草稿保存状态与完整 Trace。
        """
        state = _initial_state(material_id, self.user_confirmed)
        trace: List[Dict[str, Any]] = []
        terminal_action: Optional[str] = None
        terminal_reason = ""

        for step in range(1, self.max_steps + 1):
            decision = self.llm.decide(state)
            action = decision["action"]
            params = decision.get("params", {})

            # 终结类动作：不调用工具，直接收尾
            if action in ("block", "finish", "request_confirmation"):
                terminal_action = action
                terminal_reason = params.get("reason", decision.get("rationale", ""))
                trace.append(
                    {
                        "step": step,
                        "action": action,
                        "tool_arguments": params,
                        "observation_summary": f"终结动作：{decision['rationale']}",
                        "decision_rationale": decision["rationale"],
                    }
                )
                break

            tool_response = self._execute_action(action, params, state)
            self._update_state(action, tool_response, state)
            trace.append(
                {
                    "step": step,
                    "action": action,
                    "tool_arguments": tool_response.get("arguments", params),
                    "observation_summary": _summarize(tool_response),
                    "decision_rationale": decision["rationale"],
                }
            )
        else:
            # for 循环正常结束意味着达到步数上限仍未终结
            terminal_action = "step_limit"
            terminal_reason = f"达到最大步数 {self.max_steps}，任务未完成"

        return self._build_result(state, trace, terminal_action, terminal_reason)

    # ---------- 工具执行 ----------
    def _execute_action(
        self, action: str, params: Dict[str, Any], state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """根据决策动作调用对应工具。"""
        material_id = state["material_id"]

        if action == "read_material":
            return tools.read_material(self.store, material_id)

        if action == "recheck_material":
            return tools.read_material(self.store, material_id, recheck=True)

        if action == "check_rules":
            return tools.check_rules(self.store, state["material"])

        if action == "query_slot":
            return tools.query_slot(self.store, params["slot"])

        if action == "query_alternative":
            # 替代时段来自上一次时段查询的观察结果
            target = state["last_next_available"]
            if target is None:
                target = self.store.find_next_available_slot(
                    after_slot=state["current_slot"]
                )
            if target is None:
                return {
                    "ok": True,
                    "tool": "slot_query",
                    "arguments": {"slot": None},
                    "result": {"slot": None, "occupied": True, "next_available_slot": None},
                }
            return tools.query_slot(self.store, target)

        if action == "save_draft":
            risk_reasons = [v["reason"] for v in state["violations"]]
            pending: List[str] = []
            if params.get("alternative"):
                pending.append(
                    f"请求时段已被占用，建议替代时段 {params['slot']}，待用户确认"
                )
            return tools.save_draft(
                self.store,
                material_id=material_id,
                scheduled_slot=params["slot"],
                review_status="pending_confirmation" if pending else "approved",
                risk_reasons=risk_reasons,
                pending_confirmations=pending,
                alternative_slot=params.get("alternative", False),
            )

        # 未知动作：返回失败响应，由状态更新逻辑安全处理
        return {
            "ok": False,
            "tool": action,
            "arguments": params,
            "error": f"未知动作 {action}",
        }

    # ---------- 状态更新 ----------
    def _update_state(
        self, action: str, response: Dict[str, Any], state: Dict[str, Any]
    ) -> None:
        """根据工具观察结果更新状态，供下一轮模型决策使用。"""
        if action == "read_material":
            if response["ok"]:
                state["material"] = response["result"]
            else:
                state["read_error"] = response["error"]
            return

        if action == "recheck_material":
            state["recheck_done"] = True
            if response["ok"]:
                result = response["result"]
                state["recheck_resolved"] = result.get("recheck_resolved", False)
                if state["recheck_resolved"]:
                    state["material"] = result
            else:
                state["recheck_resolved"] = False
            return

        if action == "check_rules":
            result = response["result"]
            state["rule_checked"] = True
            state["rule_passed"] = result["passed"]
            state["violations"] = result["violations"]
            return

        if action == "query_slot":
            result = response.get("result", {})
            state["slot_checked"] = True
            state["current_slot"] = result.get("slot")
            state["requested_slot_occupied"] = result.get("occupied", False)
            state["last_next_available"] = result.get("next_available_slot")
            return

        if action == "query_alternative":
            result = response.get("result", {})
            state["alternative_query_done"] = True
            if not result.get("occupied") and result.get("slot"):
                state["alternative_slot"] = result["slot"]
            else:
                state["alternative_slot"] = result.get("next_available_slot")
            return

        if action == "save_draft":
            state["save_done"] = True
            if response["ok"]:
                state["save_ok"] = True
                state["duplicated"] = response["result"].get("duplicated", False)
            else:
                state["save_ok"] = False
                state["save_error"] = response["error"]
            return

    # ---------- 结果组装 ----------
    def _build_result(
        self,
        state: Dict[str, Any],
        trace: List[Dict[str, Any]],
        terminal_action: str,
        terminal_reason: str,
    ) -> Dict[str, Any]:
        """组装最终交付结果。"""
        status_map = {
            "finish": "approved",
            "block": "blocked",
            "request_confirmation": "pending_confirmation",
            "step_limit": "incomplete",
        }
        review_status = status_map.get(terminal_action, "incomplete")

        # 建议时段：优先替代时段，其次当前时段
        suggested_slot = state["alternative_slot"] or state["current_slot"]

        risk_reasons = [v["reason"] for v in state["violations"]]
        pending_confirmations: List[str] = []
        if terminal_action == "request_confirmation" and state["alternative_slot"]:
            pending_confirmations.append(
                f"请求时段 {state['material']['requested_time']} 已占用，"
                f"建议替代时段 {state['alternative_slot']}，待用户确认"
            )
        if state["save_error"]:
            risk_reasons.append(state["save_error"])

        draft_saved = state["save_ok"]
        return {
            "material_id": state["material_id"],
            "review_status": review_status,
            "risk_reasons": risk_reasons,
            "suggested_slot": suggested_slot,
            "pending_confirmations": pending_confirmations,
            "draft_saved": draft_saved,
            "duplicated_submission": state["duplicated"],
            "published": False,  # 始终只是草稿
            "steps_used": len(trace),
            "llm_name": self.llm_name,
            "termination_reason": terminal_reason,
            "trace": trace,
        }
