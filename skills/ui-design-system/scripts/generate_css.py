#!/usr/bin/env python3
"""generate_css.py - tokens → CSS variables"""

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


def to_kebab(path: str) -> str:
    return "--" + path.replace(".", "-").lower()


def main():
    parser = argparse.ArgumentParser(description="生成 CSS variables")
    parser.add_argument("--tokens", required=True)
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()

    tokens = json.loads(Path(args.tokens).read_text(encoding="utf-8"))
    lines = [":root {"]
    for path, val in flatten(tokens):
        lines.append(f"  {to_kebab(path)}: {val};")
    lines.append("}")
    lines.append("")

    output = "\n".join(lines)
    Path(args.output).write_text(output, encoding="utf-8")
    print(f"✅ 已生成: {args.output}（{len(flatten(tokens))} 个变量）")


if __name__ == "__main__":
    main()
