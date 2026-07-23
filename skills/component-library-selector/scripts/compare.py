#!/usr/bin/env python3
"""compare.py - 库与库多维度对比"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="两个组件库对比")
    parser.add_argument("--a", required=True, help="库 A 的 id")
    parser.add_argument("--b", required=True, help="库 B 的 id")
    args = parser.parse_args()

    data_path = Path(__file__).parent.parent / "data" / "libraries.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    libs = {l["id"]: l for l in data["libraries"]}
    if args.a not in libs or args.b not in libs:
        print(f"❌ 库 id 无效: {args.a} / {args.b}", file=sys.stderr)
        print(f"   可用: {', '.join(libs.keys())}", file=sys.stderr)
        sys.exit(1)

    a, b = libs[args.a], libs[args.b]
    dimensions = data["dimensions"]

    print(f"⚖️  对比: {a['name']} vs {b['name']}\n")
    print(f"{'维度':<18} {a['name']:<20} {b['name']:<20} {'差异':>8}")
    print("-" * 70)
    for dim_key, dim_meta in dimensions.items():
        sa = a["scores"].get(dim_key, 0)
        sb = b["scores"].get(dim_key, 0)
        diff = sa - sb
        icon = "✅" if diff > 0 else "❌" if diff < 0 else "➖"
        print(f"{dim_meta['description'][:14]:<18} {sa:<20} {sb:<20} {icon} {abs(diff)}")
    print()

    # 总分
    wa = sum(a["scores"][d] * m["weight"] for d, m in dimensions.items())
    wb = sum(b["scores"][d] * m["weight"] for d, m in dimensions.items())
    winner = a["name"] if wa > wb else b["name"] if wb > wa else "平局"
    print(f"📊 加权总分: {a['name']} {wa:.1f} | {b['name']} {wb:.1f}")
    print(f"🏆 推荐: {winner}")


if __name__ == "__main__":
    main()
