# examples 目录说明

本目录存放各场景的输入、实际输出与完整 Trace。每个 JSON 文件包含最终交付结果及其完整执行 Trace（步骤、工具入参、观察摘要、决策依据）。

## Trace 文件索引

| 文件 | 场景 | 最终状态 |
|---|---|---|
| traces/trace_M02_normal.json | 正常排期 | approved |
| traces/trace_M03_missing.json | 素材信息缺失（补查后阻断） | blocked |
| traces/trace_M04_rule_risk.json | 规则风险（时长超限） | blocked |
| traces/trace_M01_conflict_unconfirmed.json | 时段冲突，等待用户确认 | pending_confirmation |
| traces/trace_M01_conflict_confirmed.json | 时段冲突，用户确认后保存 | approved |
| traces/trace_M05_repeat_1.json | 重复提交第一次 | approved |
| traces/trace_M05_repeat_2.json | 重复提交第二次（幂等拦截） | approved，duplicated=true |
| traces/trace_M02_save_fail.json | 保存失败注入 | blocked |

## 复现命令

```bash
python run.py --material M02 --tag normal
python run.py --material M03 --tag missing
python run.py --material M04 --tag rule_risk
python run.py --material M01 --tag conflict_unconfirmed
python run.py --material M01 --confirm --tag conflict_confirmed
python run.py --material M05 --repeat 2
python run.py --material M02 --simulate-save-fail --tag save_fail
```
