#!/usr/bin/env python3
"""export_images.py - 导出 Figma 节点为 PNG/JPG/SVG/PDF"""

import argparse
import sys
import time
from pathlib import Path

from client import FigmaClient, FigmaError, download_image


def main():
    parser = argparse.ArgumentParser(description="导出 Figma 节点为图片")
    parser.add_argument("--file-key", required=True, help="Figma file key")
    parser.add_argument("--node-ids", required=True, help="逗号分隔的 node-id")
    parser.add_argument("--format", default="png", choices=["png", "jpg", "svg", "pdf"])
    parser.add_argument("--scale", type=float, default=2.0, help="缩放比例 1-4")
    parser.add_argument("--output-dir", default="./images", help="输出目录")
    parser.add_argument("--mock", action="store_true", help="强制使用 mock 数据")
    args = parser.parse_args()

    node_ids = [n.strip() for n in args.node_ids.split(",") if n.strip()]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        client = FigmaClient(mock=args.mock)
        # 1) 拿临时下载 URL
        images_resp = client.get_images(args.file_key, node_ids, args.format, args.scale)
    except FigmaError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    image_map = images_resp.get("images", {})
    if not image_map:
        print("⚠️ 未返回任何图片", file=sys.stderr)
        sys.exit(1)

    # 2) 下载每张图
    for node_id, url in image_map.items():
        if not url:
            print(f"⏭️ 跳过 {node_id}（无 URL）")
            continue
        ext = "jpg" if args.format == "jpg" else args.format
        out_path = output_dir / f"{node_id.replace(':', '-')}.{ext}"
        try:
            size = download_image(url, out_path)
            print(f"✅ {out_path} ({size} bytes)")
        except Exception as e:
            print(f"❌ {node_id}: {e}", file=sys.stderr)
        time.sleep(0.2)  # 礼貌限流

    print(f"📁 输出目录: {output_dir}")


if __name__ == "__main__":
    main()
