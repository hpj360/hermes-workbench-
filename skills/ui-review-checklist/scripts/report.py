#!/usr/bin/env python3
"""report.py - 生成 Markdown 评审报告"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="生成 UI 评审报告")
    parser.add_argument("--scan-result", required=True)
    parser.add_argument("--score-result", help="评分 JSON")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()

    scan = json.loads(Path(args.scan_result).read_text(encoding="utf-8"))
    score = json.loads(Path(args.score_result).read_text(encoding="utf-8")) if args.score_result else {}

    findings = scan["findings"]
    anti = findings["anti_patterns"]
    a11y = findings["a11y_issues"]

    # 按 id 聚合
    anti_by_id = Counter(f["id"] for f in anti)
    a11y_by_id = Counter(f["id"] for f in a11y)

    lines = [
        f"# UI 评审报告",
        "",
        f"**目标**: `{scan['target']}`",
        f"**文件数**: {scan['files_scanned']}",
        "",
    ]

    if score:
        icon = "✅" if score.get("passed") else "❌"
        lines.extend([
            f"## {icon} 综合评分: {score.get('score', '?')} / 100（{score.get('grade', '?')}）",
            "",
            f"- 反模式扣分: -{score.get('breakdown', {}).get('anti_patterns', 0):.1f}",
            f"- a11y 扣分:   -{score.get('breakdown', {}).get('a11y_issues', 0)}",
            "",
        ])

    lines.extend([
        f"## 反模式（{len(anti)} 处）",
        "",
    ])
    if anti:
        lines.append("| ID | 名称 | 严重度 | 命中数 | 修复建议 |")
        lines.append("|----|------|--------|--------|----------|")
        for f in anti:
            pass
        # 聚合
        for pid, count in anti_by_id.most_common():
            sample = next((f for f in anti if f["id"] == pid), {})
            lines.append(f"| {pid} | {sample.get('name', '?')} | {sample.get('severity', '?')} | {count} | {sample.get('fix', '')} |")
    else:
        lines.append("无")

    lines.extend(["", f"## a11y 问题（{len(a11y)} 处）", ""])
    if a11y:
        for pid, count in a11y_by_id.most_common():
            sample = next((f for f in a11y if f["id"] == pid), {})
            lines.append(f"- **{sample.get('name', '?')}**：{count} 处")
    else:
        lines.append("无")

    Path(args.output).write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 报告已生成: {args.output}")


if __name__ == "__main__":
    main()
