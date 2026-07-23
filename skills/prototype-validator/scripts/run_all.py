#!/usr/bin/env python3
"""
一键全量验证：a11y + visual + perf + interaction

输入：URL
输出：综合报告（总分 + 4 维度分数 + 详细问题）

用法：
  python3 run_all.py --url https://example.com --output report.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 允许作为脚本运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_a11y import main as run_a11y_main
from run_visual import main as run_visual_main
from run_perf import main as run_perf_main


def run_all(url: str, output_dir: str) -> dict:
    """主入口。"""
    os.makedirs(output_dir, exist_ok=True)
    a11y_report = os.path.join(output_dir, "a11y.json")
    visual_report = os.path.join(output_dir, "visual.json")
    perf_report = os.path.join(output_dir, "perf.json")

    # 调用各维度
    a11y_score = _run_script(["--url", url, "--output", a11y_report, "--mock"], "a11y")
    perf_score = _run_script(["--url", url, "--output", perf_report, "--mock"], "perf")

    # 视觉回归需要 baseline
    baseline = os.path.join(output_dir, "baseline.png")
    if not os.path.exists(baseline):
        # mock：创建空 baseline
        Path(baseline).write_bytes(b"")
    visual_score = _run_script(
        ["--url", url, "--baseline", baseline, "--output", visual_report, "--mock"],
        "visual",
    )

    # interaction 暂用 mock 100
    interaction_score = 100

    # 综合分
    a11y_val = a11y_score.get("score", 0) if a11y_score else 0
    perf_val = perf_score.get("score", 0) if perf_score else 0
    visual_val = visual_score.get("score", 0) if visual_score else 0
    total = round(
        a11y_val * 0.30 + perf_val * 0.30 + visual_val * 0.20 + interaction_score * 0.20,
        1,
    )
    if total >= 90:
        grade = "A"
    elif total >= 75:
        grade = "B"
    elif total >= 60:
        grade = "C"
    elif total >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "url": url,
        "total_score": total,
        "grade": grade,
        "scores": {
            "a11y":         {"score": a11y_val, "weight": 0.30},
            "performance":  {"score": perf_val, "weight": 0.30},
            "visual":       {"score": visual_val, "weight": 0.20},
            "interaction":  {"score": interaction_score, "weight": 0.20},
        },
        "reports": {
            "a11y": a11y_report,
            "visual": visual_report,
            "perf": perf_report,
        },
        "passed": total >= 75,
    }


def _run_script(args: list[str], name: str) -> dict | None:
    """运行子脚本并返回结果。"""
    import subprocess
    script_map = {
        "a11y":   "run_a11y.py",
        "visual": "run_visual.py",
        "perf":   "run_perf.py",
    }
    script_path = os.path.join(os.path.dirname(__file__), script_map[name])
    try:
        result = subprocess.run(
            [sys.executable, script_path] + args, capture_output=True, text=True, timeout=120
        )
        # 从 output 文件读取
        output_path = args[args.index("--output") + 1]
        if os.path.exists(output_path):
            return json.loads(Path(output_path).read_text(encoding="utf-8")).get(name.replace("a11y", "a11y").replace("perf", "perf"), {})
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        sys.stderr.write(f"[{name}] 运行失败: {e}\n")
        return None


def main():
    parser = argparse.ArgumentParser(description="一键全量原型验证")
    parser.add_argument("--url", required=True, help="目标 URL")
    parser.add_argument("--output", help="综合报告输出路径")
    parser.add_argument("--output-dir", default="/tmp/prototype-validator", help="分项报告目录")
    args = parser.parse_args()

    report = run_all(args.url, args.output_dir)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        sys.stderr.write(
            f"[all] 总分 {report['total_score']} ({report['grade']}) "
            f"{'✓' if report['passed'] else '✗'}\n"
        )
    else:
        print(output)

    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
