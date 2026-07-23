#!/usr/bin/env python3
"""
sync.py - 多端 token 同步主入口

DTCG JSON → 8 端产物
"""

import argparse
import json
import sys
from pathlib import Path

from resolve import flatten_dtcg, resolve_aliases, is_color


def fmt_css(resolved: dict, group_by: bool = True) -> str:
    """CSS variables"""
    lines = [":root {"]
    for path, val in sorted(resolved.items()):
        key = "--" + path.replace(".", "-").lower()
        lines.append(f"  {key}: {val};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def fmt_scss(resolved: dict) -> str:
    """SCSS variables"""
    lines = []
    for path, val in sorted(resolved.items()):
        key = path.replace(".", "-").lower()
        lines.append(f"${key}: {val};")
    return "\n".join(lines) + "\n"


def fmt_js(resolved: dict) -> str:
    """JS object"""
    obj = {}
    for path, val in resolved.items():
        parts = path.split(".")
        cur = obj
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = val
    return "export const tokens = " + json.dumps(obj, indent=2) + ";\n"


def fmt_ts(resolved: dict) -> str:
    """TS object (with type)"""
    obj = {}
    for path, val in resolved.items():
        parts = path.split(".")
        cur = obj
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = val
    return "export const tokens = " + json.dumps(obj, indent=2) + " as const;\n"


def fmt_swift(resolved: dict) -> str:
    """Swift enum"""
    import re
    lines = ["import SwiftUI", "", "public enum Tokens {"]
    by_top: dict = {}
    for path, val in resolved.items():
        top = path.split(".")[0]
        by_top.setdefault(top, []).append((path, val))

    for top, items in by_top.items():
        lines.append(f"    public enum {top.title()} {{")
        for path, val in items:
            name = path.split(".", 1)[1].replace(".", "_").replace("-", "_")
            s = str(val)
            if re.match(r"^#[0-9A-Fa-f]{3,8}$", s):
                h = s.lstrip("#")
                if len(h) == 3:
                    h = "".join(c * 2 for c in h)
                a = h[6:8] if len(h) == 8 else "FF"
                r, g, b = h[0:2], h[2:4], h[4:6]
                swift_val = f"Color(red: 0x{r}/255, green: 0x{g}/255, blue: 0x{b}/255, opacity: 0x{a}/255)"
            elif s.endswith("px"):
                swift_val = f"CGFloat({s.replace('px', '')})"
            else:
                swift_val = f'"{s}"'
            lines.append(f"        public static let {name} = {swift_val}")
        lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def fmt_android(resolved: dict) -> str:
    """Android XML (colors + dimens)"""
    colors = []
    dimens = []
    for path, val in resolved.items():
        s = str(val)
        key = path.replace(".", "_").replace("-", "_").lower()
        if is_color(s):
            h = s.lstrip("#").upper()
            if len(h) == 6:
                h = "FF" + h
            colors.append(f'    <color name="{key}">#{h}</color>')
        elif s.endswith("px") or s.endswith("dp"):
            n = s.replace("px", "").replace("dp", "")
            dimens.append(f'    <dimen name="{key}">{n}dp</dimen>')

    out = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
    if colors:
        out.append("    <!-- Colors -->")
        out.extend(colors)
    if dimens:
        out.append("    <!-- Dimens -->")
        out.extend(dimens)
    out.append("</resources>")
    return "\n".join(out) + "\n"


def fmt_flutter(resolved: dict) -> str:
    """Flutter Dart"""
    lines = ["import 'package:flutter/material.dart';", "", "class AppTokens {"]
    for path, val in sorted(resolved.items()):
        name = path.replace(".", "_").replace("-", "_")
        s = str(val)
        if is_color(s):
            h = s.lstrip("#")
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            dart_val = f"Color(0xFF{h.upper()})"
        else:
            dart_val = f"'{s}'"
        lines.append(f"  static const {name} = {dart_val};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def fmt_compose(resolved: dict) -> str:
    """Jetpack Compose Kotlin"""
    import re
    lines = ["package com.example.tokens", "", "import androidx.compose.ui.graphics.Color", "", "object AppTokens {"]
    for path, val in sorted(resolved.items()):
        name = path.replace(".", "_").replace("-", "_")
        s = str(val)
        if re.match(r"^#[0-9A-Fa-f]{6}$", s):
            kotlin_val = f"Color(0xFF{s.lstrip('#').upper()})"
        elif re.match(r"^[\d.]+px$", s):
            n = s.replace("px", "")
            kotlin_val = f"{n}.dp"
        else:
            kotlin_val = f'"{s}"'
        lines.append(f"    val {name} = {kotlin_val}")
    lines.append("}")
    return "\n".join(lines) + "\n"


FORMATTERS = {
    "css":     ("tokens.css",       fmt_css),
    "scss":    ("tokens.scss",      fmt_scss),
    "js":      ("tokens.js",        fmt_js),
    "ts":      ("tokens.ts",        fmt_ts),
    "swift":   ("Tokens.swift",     fmt_swift),
    "android": ("tokens.xml",       fmt_android),
    "flutter": ("tokens.dart",      fmt_flutter),
    "compose": ("Tokens.kt",        fmt_compose),
}


def main():
    parser = argparse.ArgumentParser(description="DTCG token 多端同步")
    parser.add_argument("--input", required=True, help="DTCG JSON 路径")
    parser.add_argument("--output-dir", "-o", required=True, help="输出目录")
    parser.add_argument("--platforms", default=",".join(FORMATTERS.keys()),
                        help=f"逗号分隔，可用: {','.join(FORMATTERS.keys())}")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 输入文件不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    raw = json.loads(input_path.read_text(encoding="utf-8"))
    tokens = flatten_dtcg(raw)
    resolved = resolve_aliases(tokens)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    for p in platforms:
        if p not in FORMATTERS:
            print(f"⚠️  未知平台: {p}（跳过）", file=sys.stderr)
            continue
        filename, formatter = FORMATTERS[p]
        out = formatter(resolved)
        out_path = output_dir / filename
        out_path.write_text(out, encoding="utf-8")
        print(f"✅ {p:<10} → {out_path}（{len(resolved)} tokens）")


if __name__ == "__main__":
    main()
