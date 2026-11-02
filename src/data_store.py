"""内存数据存储层。

负责加载 data/ 目录下的合成数据（素材、规则、已有排期），
并在运行期间维护草稿状态。所有数据仅保存在内存中，不进行任何真实发布。

同时提供 save_failure 注入开关，用于模拟“保存失败”场景。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class DataStore:
    """基于 JSON 文件的内存数据仓库。"""

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self._materials: Dict[str, Dict[str, Any]] = {}
        self._rules: List[Dict[str, Any]] = []
        self._occupied: Dict[str, Dict[str, Any]] = {}
        self._candidate_slots: List[str] = []
        # 草稿表：key 为素材 ID，value 为草稿内容。同一素材只保留一份草稿。
        self._drafts: Dict[str, Dict[str, Any]] = {}
        # 保存失败注入开关：打开后所有保存动作返回失败。
        self.save_failure: bool = False
        self.load()

    def load(self) -> None:
        """从 JSON 文件加载全部基础数据。"""
        materials_path = self.data_dir / "materials.json"
        rules_path = self.data_dir / "rules.json"
        schedule_path = self.data_dir / "schedule.json"

        with materials_path.open("r", encoding="utf-8") as f:
            material_data = json.load(f)
        for material in material_data["materials"]:
            self._materials[material["material_id"]] = material

        with rules_path.open("r", encoding="utf-8") as f:
            rule_data = json.load(f)
        self._rules = rule_data["rules"]

        with schedule_path.open("r", encoding="utf-8") as f:
            schedule_data = json.load(f)
        self._occupied = schedule_data["occupied"]
        self._candidate_slots = schedule_data["candidate_slots"]

    # ---------- 素材相关 ----------
    def get_material(self, material_id: str) -> Optional[Dict[str, Any]]:
        """按 ID 获取素材，不存在返回 None。"""
        return self._materials.get(material_id)

    # ---------- 规则相关 ----------
    def get_rules(self) -> List[Dict[str, Any]]:
        """获取全部审核规则。"""
        return self._rules

    # ---------- 时段相关 ----------
    def is_slot_occupied(self, slot: str) -> bool:
        """判断指定时段是否已被占用。"""
        return slot in self._occupied

    def get_slot_owner(self, slot: str) -> Optional[Dict[str, Any]]:
        """获取占用某时段的排期信息。"""
        return self._occupied.get(slot)

    def find_next_available_slot(
        self, after_slot: Optional[str] = None
    ) -> Optional[str]:
        """从候选时段中返回 after_slot 之后（含自身之后）的第一个空闲时段。"""
        start_index = 0
        if after_slot is not None:
            if after_slot in self._candidate_slots:
                start_index = self._candidate_slots.index(after_slot) + 1
            else:
                # 请求时段不在候选表中时，从头开始找空闲时段。
                start_index = 0
        for slot in self._candidate_slots[start_index:]:
            if slot not in self._occupied and slot not in self._draft_slots():
                return slot
        return None

    def _draft_slots(self) -> List[str]:
        """返回已被草稿占用的时段列表。"""
        return [draft["scheduled_slot"] for draft in self._drafts.values()]

    # ---------- 草稿相关 ----------
    def has_draft(self, material_id: str) -> bool:
        """判断素材是否已存在草稿。"""
        return material_id in self._drafts

    def get_draft(self, material_id: str) -> Optional[Dict[str, Any]]:
        """获取素材的现有草稿。"""
        return self._drafts.get(material_id)

    def save_draft(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        """保存草稿。

        幂等规则：同一 material_id 重复提交时，不新建草稿，直接返回已有草稿，
        并在返回值中标记 duplicated=True。

        返回值包含 ok 字段：
        - 保存失败注入开启时 ok=False，且不会写入任何草稿。
        - 正常情况 ok=True。
        """
        material_id = draft["material_id"]

        if self.save_failure:
            return {
                "ok": False,
                "error": "存储服务不可用，草稿保存失败",
                "duplicated": False,
            }

        if material_id in self._drafts:
            existing = self._drafts[material_id]
            return {
                "ok": True,
                "duplicated": True,
                "draft": existing,
                "message": "该素材已存在草稿，重复提交未产生新草稿",
            }

        self._drafts[material_id] = draft
        return {
            "ok": True,
            "duplicated": False,
            "draft": draft,
            "message": "草稿保存成功（仅草稿，未真实发布）",
        }

    def list_drafts(self) -> List[Dict[str, Any]]:
        """列出当前全部草稿。"""
        return list(self._drafts.values())

    def reset_runtime_state(self) -> None:
        """清空运行期草稿并关闭失败注入（基础数据保留）。"""
        self._drafts.clear()
        self.save_failure = False
