#!/usr/bin/env python3
"""export_components.py - 导出 Figma 组件元数据"""

import argparse
import json
import sys
from pathlib import Path

from client import FigmaClient, FigmaError


def main():
    parser = argparse.ArgumentParser(description="导出 Figma 组件元数据")
    parser.add_argument("--file-key", required=True, help="Figma file key")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径")
    parser.add_argument("--mock", action="store_true", help="强制使用 mock 数据")
    args = parser.parse_args()

    try:
        client = FigmaClient(mock=args.mock)
        data = client.get_components(args.file_key)
    except FigmaError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    # 提取关键字段
    components = []
    for c in data.get("meta", {}).get("components", []):
        components.append({
            "key": c.get("key"),
            "node_id": c.get("node_id"),
            "name": c.get("name"),
            "description": c.get("description", ""),
            "containing_frame": c.get("containing_frame", {}).get("name"),
        })

    result = {"file_key": args.file_key, "count": len(components), "components": components}

    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 已写入: {args.output}（{len(components)} 个组件）")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
