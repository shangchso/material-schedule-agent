"""Agent 可执行测试（标准库 unittest，无需第三方依赖）。

运行方式（在项目根目录）：
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

from src.agent import SchedulingAgent
from src.data_store import DataStore
from src.llm import MockLLM

# 测试中数据目录固定指向项目根目录下的 data/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class SchedulingAgentTest(unittest.TestCase):
    """覆盖全部官方验收点的测试用例。"""

    def setUp(self) -> None:
        self.store = DataStore(DATA_DIR)
        self.llm = MockLLM()

    def _run(self, material_id: str, user_confirmed: bool = False,
             max_steps: int = 8) -> dict:
        agent = SchedulingAgent(
            self.store,
            llm=self.llm,
            max_steps=max_steps,
            user_confirmed=user_confirmed,
        )
        return agent.run(material_id)

    def test_normal_schedule(self) -> None:
        """验收点1：正常排期，审核通过且草稿保存成功。"""
        result = self._run("M02")
        self.assertEqual(result["review_status"], "approved")
        self.assertTrue(result["draft_saved"])
        self.assertEqual(result["suggested_slot"], "19:00")
        self.assertFalse(result["published"])

    def test_missing_information(self) -> None:
        """验收点2：素材信息缺失，补查后仍缺失则阻断。"""
        result = self._run("M03")
        self.assertEqual(result["review_status"], "blocked")
        self.assertFalse(result["draft_saved"])
        # Trace 中必须包含一次补查动作
        actions = [step["action"] for step in result["trace"]]
        self.assertIn("recheck_material", actions)

    def test_rule_risk(self) -> None:
        """验收点3：规则风险，明确返回风险原因并阻断。"""
        result = self._run("M04")
        self.assertEqual(result["review_status"], "blocked")
        self.assertTrue(
            any("超过上限" in reason for reason in result["risk_reasons"])
        )

    def test_slot_conflict_waiting_confirmation(self) -> None:
        """验收点4a：时段冲突，返回替代时段并请求确认。"""
        result = self._run("M01")
        self.assertEqual(result["review_status"], "pending_confirmation")
        self.assertEqual(result["suggested_slot"], "19:00")
        self.assertEqual(len(result["pending_confirmations"]), 1)
        self.assertFalse(result["draft_saved"])

    def test_slot_conflict_after_confirmation(self) -> None:
        """验收点4b：用户确认替代时段后，草稿保存成功。"""
        result = self._run("M01", user_confirmed=True)
        self.assertEqual(result["review_status"], "approved")
        self.assertTrue(result["draft_saved"])

    def test_duplicate_submission(self) -> None:
        """验收点5：重复提交只产生一份草稿。"""
        first = self._run("M05")
        self.assertTrue(first["draft_saved"])
        self.assertFalse(first["duplicated_submission"])

        second = self._run("M05")
        self.assertTrue(second["draft_saved"])
        self.assertTrue(second["duplicated_submission"])
        # 仓库中该素材仍然只有一份草稿
        self.assertEqual(len(self.store.list_drafts()), 1)

    def test_save_failure(self) -> None:
        """验收点6：保存失败必须如实返回，不得虚报成功。"""
        self.store.save_failure = True
        result = self._run("M02")
        self.assertEqual(result["review_status"], "blocked")
        self.assertFalse(result["draft_saved"])
        self.assertTrue(
            any("保存失败" in reason for reason in result["risk_reasons"])
        )

    def test_material_not_found(self) -> None:
        """补充场景：素材不存在时阻断。"""
        result = self._run("M404")
        self.assertEqual(result["review_status"], "blocked")
        self.assertFalse(result["draft_saved"])

    def test_step_limit_returns_incomplete(self) -> None:
        """保护机制：达到步数上限时返回明确的未完成状态。"""
        result = self._run("M01", max_steps=2)
        self.assertEqual(result["review_status"], "incomplete")
        self.assertIn("最大步数", result["termination_reason"])


if __name__ == "__main__":
    unittest.main()
