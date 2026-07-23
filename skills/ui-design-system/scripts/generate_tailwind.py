#!/usr/bin/env python3
"""generate_tailwind.py - tokens → tailwind.config.js"""

import argparse
import json
import sys
from pathlib import Path


def flatten(obj, prefix=""):
    out = []
    for k, v in obj.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.extend(flatten(v, path))
        else:
            out.append((path, v))
    return out


def to_tw_key(path: str) -> str:
    return path.replace(".", "-").lower()


def main():
    parser = argparse.ArgumentParser(description="生成 tailwind.config.js")
    parser.add_argument("--tokens", required=True)
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()

    tokens = json.loads(Path(args.tokens).read_text(encoding="utf-8"))
    lines = ["module.exports = {", "  theme: {", "    extend: {"]

    for category in ["color", "font", "space", "radius", "shadow", "motion"]:
        if category not in tokens:
            continue
        tw_name = {
            "color": "colors", "font": "fontFamily", "space": "spacing",
            "radius": "borderRadius", "shadow": "boxShadow", "motion": "transitionDuration",
        }.get(category, category)
        lines.append(f"      {tw_name}: {{")
        for path, val in flatten({category: tokens[category]}):
            key = path.split(".", 1)[1] if "." in path else path
            lines.append(f"        '{to_tw_key(key)}': '{val}',")
        lines.append("      },")

    lines.append("    },")
    lines.append("  },")
    lines.append("};")
    lines.append("")

    Path(args.output).write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 已生成: {args.output}")


if __name__ == "__main__":
    main()
