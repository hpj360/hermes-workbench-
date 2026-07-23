#!/usr/bin/env python3
"""
Playwright + axe-core 无障碍检查

输入：URL
输出：a11y 报告（按 WCAG 等级分类）

依赖：playwright + axe-core（Node.js 模式）或纯 Python axe-core
无依赖时返回 mock 报告（供沙箱开发）

用法：
  python3 run_a11y.py --url https://example.com --level AA
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _has_playwright() -> bool:
    try:
        import playwright  # noqa
        return True
    except ImportError:
        return False


def _run_playwright_axe(url: str, level: str) -> dict:
    """通过 Playwright 跑 axe-core。"""
    # 用 subprocess 调 node 脚本（避免 Python 端依赖）
    node_script = """
    const { chromium } = require('playwright');
    const { AxeBuilder } = require('@axe-core/playwright');

    (async () => {
      const browser = await chromium.launch();
      const page = await browser.newPage();
      try {
        await page.goto(process.env.TARGET_URL, { waitUntil: 'networkidle', timeout: 30000 });
        const results = await new AxeBuilder({ page })
          .withTags(process.env.AXE_TAGS ? process.env.AXE_TAGS.split(',') : ['wcag2a', 'wcag2aa'])
          .analyze();
        console.log(JSON.stringify(results, null, 2));
      } catch (e) {
        console.error('ERROR:' + e.message);
        process.exit(1);
      } finally {
        await browser.close();
      }
    })();
    """
    script_path = "/tmp/axe_runner.js"
    Path(script_path).write_text(node_script, encoding="utf-8")

    tags_map = {
        "A":   "wcag2a,wcag21a,wcag22a",
        "AA":  "wcag2a,wcag2aa,wcag21a,wcag21aa,wcag22a,wcag22aa",
        "AAA": "wcag2a,wcag2aa,wcag2aaa,wcag21a,wcag21aa,wcag21aaa,wcag22a,wcag22aa,wcag22aaa",
    }
    env = {
        **os.environ,
        "TARGET_URL": url,
        "AXE_TAGS": tags_map.get(level, tags_map["AA"]),
    }
    try:
        result = subprocess.run(
            ["node", script_path], capture_output=True, text=True, env=env, timeout=60
        )
        if result.returncode != 0:
            return {"error": f"axe-core 失败: {result.stderr}", "violations": []}
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"error": str(e), "violations": []}


def _mock_a11y_report(url: str, level: str) -> dict:
    """无 Playwright 时的 mock 报告（供沙箱/CI 验证代码路径）。"""
    return {
        "url": url,
        "level": level,
        "testEngine": {"name": "mock", "version": "0.1.0"},
        "testRunner": {"name": "prototype-validator (mock)"},
        "passes": [
            {"id": "color-contrast", "description": "颜色对比度符合 WCAG AA", "impact": "serious", "nodes": []},
            {"id": "html-has-lang", "description": "html 元素有 lang 属性", "impact": "serious", "nodes": []},
        ],
        "violations": [
            {
                "id": "image-alt",
                "description": "图片必须有 alt 属性",
                "impact": "critical",
                "help": "为 img 元素添加 alt 属性",
                "helpUrl": "https://dequeuniversity.com/rules/axe/4.7/image-alt",
                "nodes": [
                    {"html": "<img src='banner.png'>", "target": ["img"]},
                ],
            },
            {
                "id": "label",
                "description": "表单元素必须有 label",
                "impact": "serious",
                "help": "添加 <label> 或 aria-label",
                "helpUrl": "https://dequeuniversity.com/rules/axe/4.7/label",
                "nodes": [
                    {"html": "<input type='text'>", "target": ["input"]},
                ],
            },
        ],
        "incomplete": [],
        "inapplicable": [],
        "_mock": True,
    }


def _score_a11y(report: dict) -> dict:
    """根据 violations 计算 a11y 分数。"""
    if report.get("error"):
        return {"score": 0, "error": report["error"]}

    violations = report.get("violations", [])
    by_impact = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
    for v in violations:
        impact = v.get("impact", "minor")
        by_impact[impact] = by_impact.get(impact, 0) + 1
    score = max(0, 100 - by_impact["critical"] * 10 - by_impact["serious"] * 5 - by_impact["moderate"] * 2 - by_impact["minor"])
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
        "violations_by_impact": by_impact,
        "total_violations": len(violations),
    }


def main():
    parser = argparse.ArgumentParser(description="Playwright + axe-core 无障碍检查")
    parser.add_argument("--url", required=True, help="目标 URL")
    parser.add_argument("--level", default="AA", choices=["A", "AA", "AAA"], help="WCAG 等级")
    parser.add_argument("--output", help="输出 JSON 路径（默认 stdout）")
    parser.add_argument("--mock", action="store_true", help="强制 mock 模式（沙箱）")
    args = parser.parse_args()

    if args.mock or not _has_playwright():
        if not args.mock:
            sys.stderr.write("[a11y] 提示: 未安装 playwright，使用 mock 模式\n")
        report = _mock_a11y_report(args.url, args.level)
    else:
        report = _run_playwright_axe(args.url, args.level)

    score = _score_a11y(report)
    output = {
        "url": args.url,
        "level": args.level,
        "tool": "playwright + axe-core" if not report.get("_mock") else "mock",
        "a11y": score,
        "violations": report.get("violations", []),
        "passes_count": len(report.get("passes", [])),
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json.dumps(output, ensure_ascii=False, indent=2))
        sys.stderr.write(
            f"[a11y] 评分 {score['score']} ({score.get('grade', '?')})，"
            f"违规 {score.get('total_violations', 0)} 条\n"
        )
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))

    # critical 违规非零退出
    if score.get("violations_by_impact", {}).get("critical", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
