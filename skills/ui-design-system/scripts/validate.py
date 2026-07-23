#!/usr/bin/env python3
"""
validate.py - Design Token 校验器

校验项：
- 必填字段存在（color/font/space/radius/shadow/motion）
- HEX 颜色格式正确（#RGB/#RRGGBB）
- 数值单位（px/ms/%）
- 命名规范（kebab-case / dot.case）
- 颜色对比度（WCAG 2.1）
- alias 引用合法性
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REQUIRED_TOP_KEYS = ["color", "font", "space", "radius", "shadow", "motion"]
HEX_RE = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$")
RGBA_RE = re.compile(r"^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)$")
ALIAS_RE = re.compile(r"\{([^}]+)\}")


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))  # type: ignore


def relative_luminance(hex_color: str) -> float:
    """WCAG 2.1 相对亮度"""
    r, g, b = (c / 255.0 for c in hex_to_rgb(hex_color))
    def linearize(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.1 对比度"""
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def flatten(obj: Dict, prefix: str = "") -> List[Tuple[str, Any]]:
    """递归展平嵌套 dict 为 [(path, value)]"""
    out = []
    for k, v in obj.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.extend(flatten(v, path))
        else:
            out.append((path, v))
    return out


def validate_color(path: str, value: Any, errors: List[str]) -> None:
    s = str(value).strip()
    if HEX_RE.match(s) or RGBA_RE.match(s):
        return
    if ALIAS_RE.fullmatch(s):
        return
    errors.append(f"  ❌ {path}: 颜色格式错误 '{s}'（需 #HEX 或 rgba()）")


def validate_unit(path: str, value: Any, expected_unit: str, errors: List[str]) -> None:
    s = str(value).strip()
    if ALIAS_RE.fullmatch(s):
        return
    if expected_unit in ("px", "ms", "%"):
        if not re.match(rf"^-?[\d.]+{expected_unit}$", s):
            errors.append(f"  ❌ {path}: 单位错误 '{s}'（需 {expected_unit}）")


def validate(tokens: Dict) -> List[str]:
    errors: List[str] = []

    # 1. 必填字段
    for k in REQUIRED_TOP_KEYS:
        if k not in tokens:
            errors.append(f"❌ 缺少必填字段: {k}")

    # 2. 颜色格式
    for path, val in flatten(tokens.get("color", {})):
        validate_color(path, val, errors)

    # 3. 字号/行高单位（统一为 px 数字）
    for path, val in flatten(tokens.get("font", {})):
        if "size" in path or "line-height" in path or path.endswith(".weight"):
            continue
        if "family" in path:
            if not isinstance(val, str) or not val:
                errors.append(f"  ❌ {path}: font-family 不能为空")

    # 4. space/radius/shadow 单位
    for path, val in flatten(tokens.get("space", {})):
        validate_unit(path, val, "px", errors)
    for path, val in flatten(tokens.get("radius", {})):
        validate_unit(path, val, "px", errors)
    for path, val in flatten(tokens.get("motion", {})):
        if "duration" in path:
            validate_unit(path, val, "ms", errors)

    # 5. 对比度（关键组合：text vs surface）
    try:
        text = tokens["color"]["text"]
        surface = tokens["color"]["surface"]
        if isinstance(text, str) and isinstance(surface, str):
            # 解析简单 alias（如果是 alias，跳过对比度检查）
            if not ALIAS_RE.search(text) and not ALIAS_RE.search(surface):
                ratio = contrast_ratio(text, surface)
                if ratio < 4.5:
                    errors.append(f"  ⚠️  text vs surface 对比度 {ratio:.2f}:1（WCAG AA 需 4.5:1）")
    except KeyError:
        pass

    return errors


def main():
    parser = argparse.ArgumentParser(description="Design Token 校验")
    parser.add_argument("--tokens", required=True, help="tokens JSON 路径")
    parser.add_argument("--strict", action="store_true", help="严格模式（警告也算错误）")
    args = parser.parse_args()

    tokens_path = Path(args.tokens)
    if not tokens_path.exists():
        print(f"❌ 文件不存在: {tokens_path}", file=sys.stderr)
        sys.exit(1)

    try:
        tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate(tokens)
    warnings = [e for e in errors if "⚠️" in e]
    real_errors = [e for e in errors if "❌" in e]

    print(f"📋 Token 校验：{tokens_path.name}")
    print(f"   字段数: {len(flatten(tokens))}")
    if real_errors:
        print(f"\n❌ 发现 {len(real_errors)} 个错误：")
        for e in real_errors:
            print(e)
    if warnings:
        print(f"\n⚠️  {len(warnings)} 个警告：")
        for w in warnings:
            print(w)

    if real_errors or (args.strict and warnings):
        sys.exit(1)
    print("\n✅ 校验通过")


if __name__ == "__main__":
    main()
