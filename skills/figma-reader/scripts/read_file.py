#!/usr/bin/env python3
"""read_file.py - 读取 Figma 完整文件"""

import argparse
import json
import sys
from pathlib import Path

from client import FigmaClient, FigmaError


def main():
    parser = argparse.ArgumentParser(description="读取 Figma 文件")
    parser.add_argument("--file-key", required=True, help="Figma file key")
    parser.add_argument("--depth", type=int, help="遍历深度（1-5）")
    parser.add_argument("--geometry", action="store_true", help="返回几何信息")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径")
    parser.add_argument("--mock", action="store_true", help="强制使用 mock 数据")
    args = parser.parse_args()

    try:
        client = FigmaClient(mock=args.mock)
        data = client.get_file(args.file_key, depth=args.depth, geometry=args.geometry)
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
