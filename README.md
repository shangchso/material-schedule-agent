# 素材审核与发布排期 Agent

小影科技 2027 校招 AI Agent 笔试题 · 第 1 题项目。

帮助内容团队对待处理素材完成审核与发布排期：Agent 依据工具返回的观察结果动态决策，输出审核状态、风险原因、建议时段、待确认项与草稿保存状态。**系统只保存草稿，不执行真实发布。**

## 1. 环境要求

- Python 3.10 及以上（验证环境 Python 3.13）。
- 仅使用标准库，无需安装第三方依赖。

## 2. 安装

```bash
# 克隆后进入项目目录
cd material-schedule-agent

# 无第三方依赖；如需确认环境可执行
python --version
```

## 3. 运行

```bash
# 查看全部素材
python run.py --list

# 正常排期
python run.py --material M02

# 信息缺失（补查后阻断）
python run.py --material M03

# 规则风险
python run.py --material M04

# 时段冲突：先返回待确认，用户确认后再执行
python run.py --material M01
python run.py --material M01 --confirm

# 重复提交（同一进程连续两次，验证幂等）
python run.py --material M05 --repeat 2

# 保存失败注入
python run.py --material M02 --simulate-save-fail
```

运行结果以 JSON 输出，完整 Trace 自动保存到 `examples/traces/`。

## 4. 测试

```bash
python -m unittest discover -s tests -v
```

预期：9 个用例全部 OK。

## 5. 评审入口

| 内容 | 位置 |
|---|---|
| 需求与成功标准 | docs/01-requirements.md |
| 方案与技术取舍 | docs/02-solution.md |
| 评估结果与限制 | docs/03-evaluation.md |
| AI 辅助使用记录 | docs/04-ai-usage.md |
| 复盘与改进 | docs/05-retrospective.md |
| 场景 Trace | examples/traces/ |
| 项目代码 | src/ |
| 可执行测试 | tests/ |

## 6. 目录结构

```
material-schedule-agent/
├── README.md
├── requirements.txt
├── .env.example
├── run.py                # CLI 入口
├── src/
│   ├── agent.py          # ReAct 主循环
│   ├── llm.py            # MockLLM / RealLLM
│   ├── data_store.py     # 内存数据与草稿
│   └── tools/            # 四个业务工具
├── tests/                # 可执行测试
├── examples/             # 输入、输出与 Trace
├── data/                 # 合成数据与规则
└── docs/                 # 五份编号文档
```

## 7. 关键边界

- 未经用户确认，不擅自修改硬性发布要求。
- 只有草稿状态，不存在已发布状态。
- 保存失败如实返回，不虚报成功。
- 默认离线 MockLLM 运行；RealLLM 需按 `.env.example` 配置环境变量后启用。
