#!/usr/bin/env python3
"""read_nodes.py - 读取 Figma 指定节点"""

import argparse
import json
import sys
from pathlib import Path

from client import FigmaClient, FigmaError


def main():
    parser = argparse.ArgumentParser(description="读取 Figma 节点")
    parser.add_argument("--file-key", required=True, help="Figma file key")
    parser.add_argument("--node-ids", required=True, help="逗号分隔的 node-id，如 1:2,3:4")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径")
    parser.add_argument("--mock", action="store_true", help="强制使用 mock 数据")
    args = parser.parse_args()

    node_ids = [n.strip() for n in args.node_ids.split(",") if n.strip()]
    if not node_ids:
        print("❌ --node-ids 不能为空", file=sys.stderr)
        sys.exit(1)

    try:
        client = FigmaClient(mock=args.mock)
        data = client.get_nodes(args.file_key, node_ids)
    except FigmaError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ 已写入: {args.output}")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
