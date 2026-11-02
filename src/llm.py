"""决策模型层。

提供两种决策实现：
1. MockLLM：离线规则式决策模型，不依赖任何外部 API，根据当前状态与
   工具观察结果决定下一步动作，是本项目默认运行方式。
2. RealLLM：基于 OpenAI 兼容 Chat Completions 接口的真实大模型实现，
   通过环境变量配置；未配置密钥时 Agent 自动回退到 MockLLM。

决策动作集合：
- read_material        读取素材
- recheck_material     补查缺失信息
- check_rules          规则检查
- query_slot           查询请求时段
- query_alternative    查询替代时段
- request_confirmation 请求用户确认（结束本轮，等待人工确认）
- save_draft           保存草稿
- block                阻断并结束
- finish               正常结束
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List


class MockLLM:
    """离线 Mock 决策模型。

    用显式策略模拟大模型的 ReAct 决策：每一步只依据 state 中已有的
    观察结果选择动作，并给出自然语言决策依据。
    """

    def decide(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """根据当前状态返回下一步动作。

        Returns:
            {"action": 动作名, "params": 动作参数, "rationale": 决策依据,
             "terminal": 是否为终结动作}
        """
        # 1. 尚未读取素材，先读取
        if state["material"] is None and not state["read_error"]:
            return {
                "action": "read_material",
                "params": {},
                "rationale": "没有任何素材信息，第一步需要读取素材",
                "terminal": False,
            }

        # 2. 素材不存在，阻断
        if state["read_error"]:
            return {
                "action": "block",
                "params": {"reason": state["read_error"]},
                "rationale": "素材无法读取，不具备排期基础，流程阻断",
                "terminal": True,
            }

        material = state["material"]

        # 3. 信息缺失：先补查一次；补查仍无法解决则阻断
        if material.get("incomplete"):
            if not state["recheck_done"]:
                return {
                    "action": "recheck_material",
                    "params": {},
                    "rationale": (
                        f"素材缺失字段 {material.get('missing_fields')}，"
                        "先补查数据源确认能否补全，而不是直接排期"
                    ),
                    "terminal": False,
                }
            if not state["recheck_resolved"]:
                return {
                    "action": "block",
                    "params": {
                        "reason": (
                            f"补查后字段 {material.get('missing_fields')} 仍缺失，"
                            "信息不足无法排期"
                        )
                    },
                    "rationale": "补查未能补全必填信息，依据完整性要求阻断",
                    "terminal": True,
                }

        # 4. 规则检查
        if not state["rule_checked"]:
            return {
                "action": "check_rules",
                "params": {},
                "rationale": "素材信息完整，下一步执行审核规则检查",
                "terminal": False,
            }

        if not state["rule_passed"]:
            return {
                "action": "block",
                "params": {"reason": "存在审核规则违规", "violations": state["violations"]},
                "rationale": "规则检查未通过，禁止进入排期环节",
                "terminal": True,
            }

        # 5. 时段查询
        if not state["slot_checked"]:
            return {
                "action": "query_slot",
                "params": {"slot": material["requested_time"]},
                "rationale": "规则通过，查询用户请求的发布时段是否可用",
                "terminal": False,
            }

        # 6. 请求时段被占用：查询替代时段
        if state["requested_slot_occupied"] and not state["alternative_query_done"]:
            return {
                "action": "query_alternative",
                "params": {"slot": state["current_slot"]},
                "rationale": (
                    f"请求时段 {material['requested_time']} 已被占用，"
                    "需要查询下一个可用时段作为替代建议"
                ),
                "terminal": False,
            }

        # 7. 替代时段处理
        if state["requested_slot_occupied"]:
            alternative = state["alternative_slot"]
            if alternative is None:
                return {
                    "action": "block",
                    "params": {"reason": "请求时段已占用且无可用替代时段"},
                    "rationale": "没有任何可替代的空闲时段，无法形成排期",
                    "terminal": True,
                }
            if not state["user_confirmed"]:
                return {
                    "action": "request_confirmation",
                    "params": {"slot": alternative},
                    "rationale": (
                        "替代时段属于对用户发布安排的变更，未经用户确认不得擅自"
                        "修改硬性发布要求，先请求人工确认"
                    ),
                    "terminal": True,
                }
            # 用户已确认替代时段：先检查保存结果，未保存才执行保存
            if state["save_done"]:
                if state["save_ok"]:
                    return {
                        "action": "finish",
                        "params": {},
                        "rationale": "替代时段草稿已保存，任务完成（仅草稿，未真实发布）",
                        "terminal": True,
                    }
                return {
                    "action": "block",
                    "params": {"reason": state["save_error"]},
                    "rationale": "草稿保存失败，如实返回失败，不虚报成功",
                    "terminal": True,
                }
            return {
                "action": "save_draft",
                "params": {"slot": alternative, "alternative": True},
                "rationale": "用户已确认替代时段，可以保存排期草稿",
                "terminal": False,
            }

        # 8. 请求时段空闲，直接保存草稿
        if not state["save_done"]:
            return {
                "action": "save_draft",
                "params": {"slot": state["current_slot"], "alternative": False},
                "rationale": "请求时段空闲且审核通过，保存排期草稿",
                "terminal": False,
            }

        # 9. 保存结果处理
        if state["save_done"]:
            if not state["save_ok"]:
                return {
                    "action": "block",
                    "params": {"reason": state["save_error"]},
                    "rationale": "草稿保存失败，如实返回失败，不虚报成功",
                    "terminal": True,
                }
            return {
                "action": "finish",
                "params": {},
                "rationale": "草稿已保存，任务完成（仅草稿，未真实发布）",
                "terminal": True,
            }

        # 理论上不会到达的兜底分支
        return {
            "action": "block",
            "params": {"reason": "决策状态异常"},
            "rationale": "未匹配到任何已知决策分支，安全阻断",
            "terminal": True,
        }


class RealLLM:
    """真实大模型决策实现（OpenAI 兼容接口）。

    环境变量：
    - LLM_API_KEY:  API 密钥（必填，未配置则不启用）
    - LLM_BASE_URL: 接口地址，默认 https://api.openai.com/v1
    - LLM_MODEL:    模型名，默认 gpt-4o-mini
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    def decide(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """调用真实大模型进行决策，要求模型返回 JSON。"""
        prompt = (
            "你是素材审核与发布排期 Agent 的决策模块。"
            "可用动作：read_material, recheck_material, check_rules, query_slot, "
            "query_alternative, request_confirmation, save_draft, block, finish。"
            "请根据当前状态选择下一步动作，只返回 JSON 对象，格式为："
            '{"action": 动作名, "params": {}, "rationale": 决策依据, "terminal": false}。'
            f"当前状态：{json.dumps(state, ensure_ascii=False)}"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        decision = json.loads(content)
        decision.setdefault("params", {})
        decision.setdefault("terminal", False)
        return decision


def build_llm() -> tuple[Any, str]:
    """构建决策模型。

    配置了 LLM_API_KEY 时使用 RealLLM，否则使用离线 MockLLM。

    Returns:
        (模型实例, 模型名称)
    """
    if os.getenv("LLM_API_KEY"):
        return RealLLM(), "RealLLM"
    return MockLLM(), "MockLLM"
