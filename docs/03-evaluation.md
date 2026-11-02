# 03 评估报告：测试预期、实际结果、失败与限制

## 1. 验证方式

- 单元测试：`python -m unittest discover -s tests -v`，共 9 个用例，全部通过。
- 端到端运行：通过 CLI 对 6 个场景逐一运行，完整结果与 Trace 存放于 `examples/traces/`。

## 2. 场景结果对照

| 场景 | 输入 | 预期 | 实际结果 | Trace 文件 |
|---|---|---|---|---|
| 正常排期 | M02 | approved，草稿保存 | approved，5 步，草稿已保存 | examples/traces/trace_M02_normal.json |
| 信息缺失 | M03 | 补查后阻断 | blocked，3 步，含一次 recheck | examples/traces/trace_M03_missing.json |
| 规则风险 | M04 | 阻断并给原因 | blocked，返回 R03 时长超限原因 | examples/traces/trace_M04_rule_risk.json |
| 时段冲突（未确认） | M01 | 待确认，不保存 | pending_confirmation，建议 19:00 | examples/traces/trace_M01_conflict_unconfirmed.json |
| 时段冲突（已确认） | M01 --confirm | 替代时段草稿保存 | approved，6 步，草稿已保存 | examples/traces/trace_M01_conflict_confirmed.json |
| 重复提交 | M05 连续两次 | 只产生一份草稿 | 第二次 duplicated=true，草稿仍为 1 份 | examples/traces/trace_M05_repeat_1.json、trace_M05_repeat_2.json |
| 保存失败 | M02 + 失败注入 | 如实返回失败 | blocked，risk_reasons 含保存失败 | examples/traces/trace_M02_save_fail.json |

## 3. 验收点覆盖确认

- A1 正常排期：覆盖（M02）。
- A2 素材信息缺失：覆盖（M03，含补查动作）。
- A3 规则风险：覆盖（M04；M06 类型不在白名单亦可触发 R02）。
- A4 时段冲突：覆盖（M01 未确认/已确认两条路径）。
- A5 重复提交：覆盖（M05 同进程两次运行）。
- A6 保存失败：覆盖（失败注入，未虚报成功）。

## 4. 失败场景与边界处理

- 素材不存在：material_reader 返回 ok=false，Agent 阻断。
- 时段格式非法：slot_query 返回参数错误。
- 无替代时段：query_alternative 观察为空时阻断。
- 达到步数上限：返回 incomplete 并注明原因。

## 5. 已知限制

1. MockLLM 是规则式决策，只验证流程与决策路径，不代表真实大模型的决策质量。
2. RealLLM 路径预留了接口但未在真实 API 上验证，评审默认以离线 Mock 结果为准。
3. 数据为合成数据，草稿仅存内存，进程结束后不保留。
4. 未提供界面与线上部署，符合题目"均非必需"的范围约定。
