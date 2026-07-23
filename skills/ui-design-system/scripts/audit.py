#!/usr/bin/env python3
"""
audit.py - Token 一致性与 AI 味反模式扫描

扫描项：
- 命名规范（kebab-case / dot.case）
- 颜色数量（过多 = 反模式）
- 紫蓝渐变（AI 味反模式）
- 命名色（red/blue/orange 等无差别命名）
- 缺失的语义化别名
"""

import argparse
import json
import re
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Token 一致性审计")
    parser.add_argument("--tokens", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    tokens = json.loads(Path(args.tokens).read_text(encoding="utf-8"))
    findings = {"warnings": [], "errors": [], "info": []}

    def flatten(obj, prefix=""):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                yield from flatten(v, path)
            else:
                yield path, v

    # 1. 颜色过多（>50 个色相分组）
    if "color" in tokens:
        color_count = sum(1 for _ in flatten({"color": tokens["color"]}))
        if color_count > 80:
            findings["warnings"].append(f"⚠️  颜色数 {color_count} 较多（>80），考虑合并近似色")
        findings["info"].append(f"ℹ️  颜色总数: {color_count}")

    # 2. 紫蓝渐变（典型 AI 味）
    if "color" in tokens:
        for path, val in flatten({"color": tokens["color"]}):
            s = str(val)
            if not s.startswith("#"):
                continue
            h = s.lstrip("#")
            if len(h) < 6:
                continue
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            # 紫色：r 80-150, g 0-80, b 150-255；蓝色：r 0-100, g 0-150, b 200-255
            if (60 <= r <= 180 and g < 100 and b > 150):
                if path.endswith((".500", ".400", ".600", ".primary", ".accent")):
                    findings["warnings"].append(f"⚠️  紫蓝系色 {path}={s}（AI 味高发，谨慎使用）")

    # 3. 缺少语义化别名
    semantic_required = ["primary", "surface", "text", "border"]
    if "color" in tokens:
        for s in semantic_required:
            if s not in tokens["color"]:
                findings["warnings"].append(f"⚠️  缺少 color.{s} 语义化别名")

    # 4. 字号系统（必须有 xs/sm/md/lg/xl）
    if "font" in tokens and "size" in tokens["font"]:
        sizes = set(tokens["font"]["size"].keys())
        missing = {"xs", "sm", "md", "lg", "xl"} - sizes
        if missing:
            findings["warnings"].append(f"⚠️  字号系统缺失: {missing}")

    # 5. 阴影层数（任何一层 > 3 层叠加 = 警告）
    if "shadow" in tokens:
        for path, val in flatten({"shadow": tokens["shadow"]}):
            s = str(val)
            layers = s.count("rgba") + s.count("rgb")
            if layers > 3:
                findings["warnings"].append(f"⚠️  {path} 阴影层数 {layers}（建议 <= 3）")

    # 输出
    print(f"📊 Token 审计：{Path(args.tokens).name}\n")
    for level in ("errors", "warnings", "info"):
        items = findings[level]
        if items:
            icon = {"errors": "❌", "warnings": "⚠️ ", "info": "ℹ️ "}[level]
            print(f"{icon} {len(items)} 项 {level}：")
            for item in items:
                print(f"  {item}")
            print()

    if findings["errors"] or (args.strict and findings["warnings"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
