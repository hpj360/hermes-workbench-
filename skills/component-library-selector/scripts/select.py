#!/usr/bin/env python3
"""
select.py - 组件库加权评分推荐

按 8 维度加权评分，支持 scenario 场景化加权。
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="组件库选型推荐")
    parser.add_argument("--scenario", default="modern-web",
                        choices=["modern-web", "enterprise", "vue3", "ai-coding", "performance", "any"])
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--framework", help="框架过滤，如 React/Vue 3")
    args = parser.parse_args()

    data_path = Path(__file__).parent.parent / "data" / "libraries.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))

    dimensions = data["dimensions"]
    scenario = data["scenarios"].get(args.scenario, data["scenarios"]["modern-web"])
    boost = scenario.get("boost", {})

    results = []
    for lib in data["libraries"]:
        # 框架过滤
        if args.framework and lib["framework"] != args.framework:
            continue
        if "filter" in scenario and scenario["filter"].get("framework"):
            if lib["framework"] not in scenario["filter"]["framework"]:
                continue

        # 加权评分
        total = 0
        for dim_key, dim_meta in dimensions.items():
            base_weight = dim_meta["weight"]
            actual_weight = base_weight * boost.get(dim_key, 1.0)
            score = lib["scores"].get(dim_key, 0)
            total += score * actual_weight

        total = round(total, 1)
        results.append((lib, total))

    results.sort(key=lambda x: -x[1])

    print(f"🏆 组件库推荐（场景: {args.scenario}）\n")
    for i, (lib, score) in enumerate(results[:args.top], 1):
        print(f"{i}. {lib['name']:<22} {score:>5.1f} / 100")
        print(f"   类型: {lib['type']:<15} 框架: {lib['framework']:<10} 许可: {lib['license']}")
        print(f"   标签: {', '.join(lib['tags'][:4])}")
        print()


if __name__ == "__main__":
    main()
