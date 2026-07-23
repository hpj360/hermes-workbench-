#!/usr/bin/env python3
"""
scan.py - UI 反模式扫描器

扫描指定目录下的源代码，检测 13 类反模式 + 13 项 a11y。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List


def load_patterns(patterns_path: Path) -> dict:
    return json.loads(patterns_path.read_text(encoding="utf-8"))


def should_scan(path: Path, file_types: List[str]) -> bool:
    return any(str(path).endswith(ft) for ft in file_types)


def scan_file(file_path: Path, patterns: List[dict], category: str) -> List[dict]:
    """扫描单个文件"""
    findings = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return findings

    for pat in patterns:
        if pat.get("manual"):
            continue
        file_types = pat.get("file_types", [])
        if not should_scan(file_path, file_types):
            continue
        try:
            regex = re.compile(pat["pattern"], re.IGNORECASE | re.MULTILINE)
        except re.error:
            continue
        for m in regex.finditer(content):
            line_no = content[:m.start()].count("\n") + 1
            findings.append({
                "category": category,
                "id": pat["id"],
                "name": pat["name"],
                "severity": pat.get("severity", "medium"),
                "file": str(file_path),
                "line": line_no,
                "match": m.group(0)[:80],
                "fix": pat.get("fix", ""),
            })
    return findings


def scan_dir(target: Path, patterns_data: dict) -> dict:
    """扫描整个目录"""
    if target.is_file():
        files = [target]
    else:
        files = [p for p in target.rglob("*") if p.is_file()]

    all_findings = {"anti_patterns": [], "a11y_issues": []}

    for f in files:
        if f.name == "patterns.json":
            continue
        all_findings["anti_patterns"].extend(
            scan_file(f, patterns_data["anti_patterns"], "anti_pattern")
        )
        all_findings["a11y_issues"].extend(
            scan_file(f, patterns_data["a11y_items"], "a11y")
        )

    return {
        "target": str(target),
        "files_scanned": len(files),
        "findings": all_findings,
        "summary": {
            "anti_patterns_count": len(all_findings["anti_patterns"]),
            "a11y_issues_count": len(all_findings["a11y_issues"]),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="UI 反模式扫描器")
    parser.add_argument("--target", required=True, help="目标目录或文件")
    parser.add_argument("--patterns", default="data/patterns.json")
    parser.add_argument("--output", "-o", help="输出 JSON 路径")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"❌ 路径不存在: {target}", file=sys.stderr)
        sys.exit(1)

    patterns_path = Path(args.patterns)
    if not patterns_path.is_absolute():
        patterns_path = Path(__file__).parent.parent / patterns_path
    if not patterns_path.exists():
        print(f"❌ patterns.json 不存在: {patterns_path}", file=sys.stderr)
        sys.exit(1)

    patterns_data = load_patterns(patterns_path)
    result = scan_dir(target, patterns_data)

    print(f"🔍 扫描: {target}")
    print(f"   文件: {result['files_scanned']}")
    print(f"   反模式命中: {result['summary']['anti_patterns_count']}")
    print(f"   a11y 问题:  {result['summary']['a11y_issues_count']}")

    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 已写入: {args.output}")


if __name__ == "__main__":
    main()
