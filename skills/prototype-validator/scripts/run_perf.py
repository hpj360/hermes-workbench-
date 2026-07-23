#!/usr/bin/env python3
"""
Lighthouse 性能审计

输入：URL
输出：性能分数 + 各项指标

依赖（可选）：lighthouse CLI（npm install -g lighthouse）
无依赖时返回 mock 报告

用法：
  python3 run_perf.py --url https://example.com
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _has_lighthouse() -> bool:
    return subprocess.run(["which", "lighthouse"], capture_output=True).returncode == 0


def _run_lighthouse(url: str) -> dict:
    """调用 lighthouse CLI。"""
    output_path = f"/tmp/lighthouse_{int(__import__('time').time())}.json"
    try:
        result = subprocess.run(
            ["lighthouse", url, "--output=json", f"--output-path={output_path}",
             "--chrome-flags=--headless --no-sandbox", "--quiet"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return {"error": f"lighthouse 失败: {result.stderr[:200]}"}
        return json.loads(Path(output_path).read_text(encoding="utf-8"))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        return {"error": str(e)}


def _mock_perf_report(url: str) -> dict:
    """无 lighthouse 时的 mock 报告。"""
    return {
        "requestedUrl": url,
        "lighthouseVersion": "12.0.0-mock",
        "categories": {
            "performance": {"score": 0.85, "title": "Performance"},
            "accessibility": {"score": 0.92, "title": "Accessibility"},
            "best-practices": {"score": 0.95, "title": "Best Practices"},
            "seo": {"score": 0.98, "title": "SEO"},
        },
        "audits": {
            "first-contentful-paint": {"numericValue": 1200, "score": 0.9, "displayValue": "1.2 s"},
            "largest-contentful-paint": {"numericValue": 2100, "score": 0.85, "displayValue": "2.1 s"},
            "total-blocking-time": {"numericValue": 150, "score": 0.95, "displayValue": "150 ms"},
            "cumulative-layout-shift": {"numericValue": 0.05, "score": 0.95, "displayValue": "0.05"},
            "speed-index": {"numericValue": 2300, "score": 0.88, "displayValue": "2.3 s"},
        },
        "_mock": True,
    }


def _score_perf(report: dict) -> dict:
    """从 lighthouse 报告计算分数。"""
    if report.get("error"):
        return {"score": 0, "error": report["error"]}
    perf = report.get("categories", {}).get("performance", {}).get("score", 0)
    score = round(perf * 100, 1)
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
    return {
        "score": score,
        "grade": grade,
        "metrics": {
            k: v.get("displayValue", "?")
            for k, v in report.get("audits", {}).items()
            if k in ("first-contentful-paint", "largest-contentful-paint", "total-blocking-time", "cumulative-layout-shift", "speed-index")
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Lighthouse 性能审计")
    parser.add_argument("--url", required=True, help="目标 URL")
    parser.add_argument("--output", help="报告输出路径")
    parser.add_argument("--mock", action="store_true", help="强制 mock")
    args = parser.parse_args()

    if args.mock or not _has_lighthouse():
        if not args.mock:
            sys.stderr.write("[perf] 提示: 未安装 lighthouse，使用 mock 模式\n")
        report = _mock_perf_report(args.url)
    else:
        report = _run_lighthouse(args.url)

    score = _score_perf(report)
    output = {
        "url": args.url,
        "tool": "lighthouse" if not report.get("_mock") else "mock",
        "perf": score,
        "categories": {
            k: round(v.get("score", 0) * 100, 1)
            for k, v in report.get("categories", {}).items()
        },
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json.dumps(output, ensure_ascii=False, indent=2))
        sys.stderr.write(f"[perf] 评分 {score['score']} ({score.get('grade', '?')})\n")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))

    if score["score"] < 75:
        sys.exit(1)


if __name__ == "__main__":
    main()
