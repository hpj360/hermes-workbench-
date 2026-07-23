#!/usr/bin/env python3
"""parse_url.py - 解析 Figma URL 提取 file_key + node_id"""

import argparse
import re
import sys
from urllib.parse import urlparse, parse_qs, unquote


def parse_figma_url(url: str) -> dict:
    """解析 Figma URL"""
    parsed = urlparse(url)

    if "figma.com" not in parsed.netloc:
        raise ValueError(f"非 Figma URL: {url}")

    # 路径形式：/file/{key}/...、/design/{key}/...、/proto/{key}/...
    path_match = re.match(r"^/(file|design|proto)/([A-Za-z0-9]+)", parsed.path)
    if not path_match:
        raise ValueError(f"无法识别 URL 路径: {parsed.path}")

    file_key = path_match.group(2)
    node_id = ""

    # node-id 可能在 query 或 path 中
    qs = parse_qs(parsed.query)
    if "node-id" in qs:
        node_id = qs["node-id"][0].replace("-", ":")
    else:
        path_node_match = re.search(r"node-id=([A-Za-z0-9%:-]+)", url)
        if path_node_match:
            node_id = unquote(path_node_match.group(1)).replace("-", ":")

    return {"file_key": file_key, "node_id": node_id, "original_url": url}


def main():
    parser = argparse.ArgumentParser(description="解析 Figma URL")
    parser.add_argument("url", help="Figma URL")
    parser.add_argument("--format", choices=["json", "kv"], default="kv", help="输出格式")
    args = parser.parse_args()

    try:
        result = parse_figma_url(args.url)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"file_key={result['file_key']} node_id={result['node_id']}")


if __name__ == "__main__":
    main()
