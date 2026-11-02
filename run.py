"""命令行入口（CLI 运行方式）。

可复制的运行命令示例：
    # 查看全部素材
    python run.py --list

    # 对某素材执行审核排期（默认离线 Mock 决策模型）
    python run.py --material M02

    # 时段冲突场景：先返回待确认；用户确认替代时段后再执行
    python run.py --material M01
    python run.py --material M01 --confirm

    # 重复提交场景：同一素材连续运行两次，共享同一数据仓库
    python run.py --material M05 --repeat 2

    # 保存失败场景：注入保存失败
    python run.py --material M02 --simulate-save-fail --tag save_fail

    # 调整最大步数
    python run.py --material M01 --max-steps 8
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from src.agent import SchedulingAgent
from src.data_store import DataStore
from src.llm import build_llm


def print_json(obj: Dict[str, Any]) -> None:
    """以可读 JSON 格式输出。"""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def list_materials(store: DataStore) -> None:
    """列出数据目录中的全部素材摘要。"""
    materials_path = Path(store.data_dir) / "materials.json"
    with materials_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    print("可用素材列表：")
    for material in data["materials"]:
        metadata = material["metadata"]
        print(
            f"  - {material['material_id']}: title={metadata.get('title')}, "
            f"type={metadata.get('type')}, 请求时段={material['requested_time']}"
        )


def save_trace(
    result: Dict[str, Any], trace_dir: Path, tag: str | None
) -> Path:
    """把 Trace 与最终结果落盘到 examples/traces/。"""
    trace_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{tag}" if tag else ""
    trace_path = trace_dir / f"trace_{result['material_id']}{suffix}.json"
    with trace_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return trace_path


def parse_args(argv: List[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="素材审核与发布排期 Agent（CLI）"
    )
    parser.add_argument("--material", "-m", help="待处理素材 ID，如 M01")
    parser.add_argument("--data-dir", default="data", help="合成数据目录，默认 data")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="用户已确认替代时段（用于确认后再次执行）",
    )
    parser.add_argument(
        "--simulate-save-fail",
        action="store_true",
        help="注入保存失败，模拟存储服务异常",
    )
    parser.add_argument("--max-steps", type=int, default=8, help="最大执行步数，默认 8")
    parser.add_argument("--repeat", type=int, default=1, help="同一素材连续运行次数，默认 1")
    parser.add_argument("--tag", default=None, help="Trace 文件名后缀标记")
    parser.add_argument(
        "--trace-dir", default="examples/traces", help="Trace 落盘目录，默认 examples/traces"
    )
    parser.add_argument("--list", action="store_true", help="列出全部素材后退出")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    """主流程。"""
    args = parse_args(argv if argv is not None else sys.argv[1:])

    store = DataStore(args.data_dir)

    if args.list:
        list_materials(store)
        return 0

    if not args.material:
        print("错误：请通过 --material 指定素材 ID，或使用 --list 查看素材", file=sys.stderr)
        return 2

    if args.simulate_save_fail:
        store.save_failure = True

    llm, llm_name = build_llm()
    results: List[Dict[str, Any]] = []

    # 同一进程内连续运行时共享 store，从而验证草稿防重复。
    for run_index in range(args.repeat):
        agent = SchedulingAgent(
            store,
            llm=llm,
            llm_name=llm_name,
            max_steps=args.max_steps,
            user_confirmed=args.confirm,
        )
        result = agent.run(args.material)
        results.append(result)

        tag = args.tag
        if args.repeat > 1:
            tag = f"{tag or 'repeat'}_{run_index + 1}"
        trace_path = save_trace(result, Path(args.trace_dir), tag)
        print(f"===== 第 {run_index + 1} 次运行结果（Trace 已保存：{trace_path}）=====")
        print_json(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
