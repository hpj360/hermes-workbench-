#!/usr/bin/env python3
"""generate_android.py - tokens → Android colors.xml/dimens.xml"""

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


def to_snake(path: str) -> str:
    return path.replace(".", "_").replace("-", "_").lower()


def main():
    parser = argparse.ArgumentParser(description="生成 Android XML")
    parser.add_argument("--tokens", required=True)
    parser.add_argument("--output-dir", "-o", required=True)
    args = parser.parse_args()

    tokens = json.loads(Path(args.tokens).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # colors.xml
    if "color" in tokens:
        lines = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
        for path, val in flatten({"color": tokens["color"]}):
            key = path.split(".", 1)[1] if "." in path else path
            v = str(val).lstrip("#").upper()
            if len(v) == 6:
                v = "FF" + v
            lines.append(f'    <color name="{to_snake(key)}">#{v}</color>')
        lines.append("</resources>")
        (output_dir / "colors.xml").write_text("\n".join(lines), encoding="utf-8")
        print(f"✅ 已生成: {output_dir}/colors.xml")

    # dimens.xml
    if "space" in tokens or "radius" in tokens:
        lines = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
        for cat in ["space", "radius"]:
            if cat not in tokens:
                continue
            for path, val in flatten({cat: tokens[cat]}):
                key = path.split(".", 1)[1] if "." in path else path
                n = str(val).replace("px", "").replace("dp", "")
                lines.append(f'    <dimen name="{to_snake(cat + "_" + key)}">{n}dp</dimen>')
        lines.append("</resources>")
        (output_dir / "dimens.xml").write_text("\n".join(lines), encoding="utf-8")
        print(f"✅ 已生成: {output_dir}/dimens.xml")


if __name__ == "__main__":
    main()
