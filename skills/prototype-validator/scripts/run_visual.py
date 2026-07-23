#!/usr/bin/env python3
"""
Playwright 视觉回归检查

输入：URL + baseline 截图路径
输出：diff 比例 + 差异图（PNG）

用法：
  python3 run_visual.py --url https://example.com --baseline baselines/home.png --current dist/current.png
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _run_playwright_screenshot(url: str, output: str, full_page: bool = True) -> bool:
    """通过 Playwright 截图。"""
    node_script = f"""
    const {{ chromium }} = require('playwright');
    (async () => {{
      const browser = await chromium.launch();
      const page = await browser.newPage({{ viewport: {{ width: 1280, height: 720 }} }});
      try {{
        await page.goto(process.env.TARGET_URL, {{ waitUntil: 'networkidle', timeout: 30000 }});
        await page.screenshot({{ path: process.env.SCREENSHOT_PATH, fullPage: process.env.FULL_PAGE === '1' }});
      }} finally {{
        await browser.close();
      }}
    }})();
    """
    script_path = "/tmp/screenshot_runner.js"
    Path(script_path).write_text(node_script, encoding="utf-8")
    env = {
        **os.environ,
        "TARGET_URL": url,
        "SCREENSHOT_PATH": output,
        "FULL_PAGE": "1" if full_page else "0",
    }
    try:
        result = subprocess.run(["node", script_path], env=env, capture_output=True, timeout=60)
        return result.returncode == 0 and os.path.exists(output)
    except subprocess.TimeoutExpired:
        return False


def _compare_images(baseline_path: str, current_path: str, diff_path: str | None) -> dict:
    """对比两张图（用 Pillow 或 mock）。"""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return {
            "diff_ratio": 0.0,
            "diff_pixels": 0,
            "total_pixels": 0,
            "error": "Pillow 未安装",
            "_mock": True,
        }

    if not os.path.exists(baseline_path):
        return {"error": f"baseline 不存在: {baseline_path}"}
    if not os.path.exists(current_path):
        return {"error": f"current 不存在: {current_path}"}

    baseline = Image.open(baseline_path).convert("RGB")
    current = Image.open(current_path).convert("RGB")
    if baseline.size != current.size:
        return {
            "error": f"尺寸不同: baseline {baseline.size} vs current {current.size}",
            "diff_ratio": 1.0,
        }

    diff = ImageChops.difference(baseline, current)
    bbox = diff.getbbox()
    if not bbox:
        return {"diff_ratio": 0.0, "diff_pixels": 0, "total_pixels": baseline.size[0] * baseline.size[1]}

    # 统计非零像素
    diff_pixels = 0
    total_pixels = baseline.size[0] * baseline.size[1]
    for pixel in diff.getdata():
        if any(p > 10 for p in pixel):
            diff_pixels += 1

    diff_ratio = diff_pixels / total_pixels
    if diff_path:
        diff.save(diff_path)

    return {
        "diff_ratio": round(diff_ratio, 6),
        "diff_pixels": diff_pixels,
        "total_pixels": total_pixels,
        "diff_bbox": bbox,
        "diff_path": diff_path,
    }


def main():
    parser = argparse.ArgumentParser(description="Playwright 视觉回归检查")
    parser.add_argument("--url", required=True, help="目标 URL")
    parser.add_argument("--baseline", required=True, help="baseline 截图路径")
    parser.add_argument("--current", help="current 截图输出路径（不指定则自动）")
    parser.add_argument("--diff", help="diff 图输出路径")
    parser.add_argument("--threshold", type=float, default=0.001, help="差异比例阈值（默认 0.1%）")
    parser.add_argument("--output", help="报告输出路径")
    parser.add_argument("--mock", action="store_true", help="强制 mock 模式")
    args = parser.parse_args()

    # 截图
    if not args.current:
        args.current = f"/tmp/visual_current_{int(__import__('time').time())}.png"
    if args.mock:
        # mock 模式：复制 baseline 当作 current
        import shutil
        if os.path.exists(args.baseline):
            shutil.copy(args.baseline, args.current)
        else:
            # 创建一个假 baseline
            Path(args.baseline).parent.mkdir(parents=True, exist_ok=True)
            Path(args.baseline).write_bytes(b"")
            Path(args.current).write_bytes(b"")
    else:
        ok = _run_playwright_screenshot(args.url, args.current)
        if not ok:
            sys.stderr.write(f"[visual] 截图失败: {args.current}\n")
            sys.exit(1)

    # 对比
    diff_result = _compare_images(args.baseline, args.current, args.diff)
    diff_ratio = diff_result.get("diff_ratio", 1.0)
    if diff_result.get("error") and not diff_result.get("_mock"):
        sys.stderr.write(f"[visual] 错误: {diff_result['error']}\n")
        sys.exit(1)

    # 评分
    if diff_ratio == 0.0:
        score = 100
    elif diff_ratio < args.threshold:
        score = 100 - (diff_ratio / args.threshold) * 5  # 微小差异扣 5 分以内
    else:
        score = max(0, 95 - (diff_ratio - args.threshold) * 1000)

    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    passed = diff_ratio < args.threshold
    output = {
        "url": args.url,
        "baseline": args.baseline,
        "current": args.current,
        "diff": diff_result,
        "score": round(score, 1),
        "grade": grade,
        "threshold": args.threshold,
        "passed": passed,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json.dumps(output, ensure_ascii=False, indent=2))
        sys.stderr.write(f"[visual] 评分 {score} ({grade})，差异 {diff_ratio*100:.4f}% {'✓' if passed else '✗'}\n")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))

    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
