#!/usr/bin/env python3
"""
score.py - UI 综合评分

从 scan.json 计算综合分（100 起始 - 反模式扣分）
"""

import argparse
import json
import sys
from pathlib import Path


SEVERITY_PENALTY = {"high": 1.0, "medium": 0.6, "low": 0.3}


def calc_score(scan_result: dict, patterns: dict) -> dict:
    score = 100
    breakdown = {"anti_patterns": 0, "a11y_issues": 0}

    pat_map = {p["id"]: p for p in patterns.get("anti_patterns", [])}

    for finding in scan_result["findings"]["anti_patterns"]:
        pat = pat_map.get(finding["id"], {})
        base_score = pat.get("score", -3)
        sev_mult = SEVERITY_PENALTY.get(finding.get("severity", "medium"), 0.6)
        penalty = abs(base_score) * sev_mult
        score -= penalty
        breakdown["anti_patterns"] += penalty

    for finding in scan_result["findings"]["a11y_issues"]:
        score -= 2
        breakdown["a11y_issues"] += 2

    score = max(0, round(score, 1))
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

    return {
        "score": score,
        "grade": grade,
        "breakdown": breakdown,
        "passed": score >= 75,
    }


def main():
    parser = argparse.ArgumentParser(description="UI 综合评分")
    parser.add_argument("--scan-result", required=True)
    parser.add_argument("--patterns", default="data/patterns.json")
    args = parser.parse_args()

    scan = json.loads(Path(args.scan_result).read_text(encoding="utf-8"))
    patterns_path = Path(args.patterns)
    if not patterns_path.is_absolute():
        patterns_path = Path(__file__).parent.parent / patterns_path
    patterns = json.loads(patterns_path.read_text(encoding="utf-8"))

    result = calc_score(scan, patterns)

    icon = "✅" if result["passed"] else "❌"
    print(f"{icon} UI 评分: {result['score']} / 100（{result['grade']}）")
    print(f"   反模式扣分: -{result['breakdown']['anti_patterns']:.1f}")
    print(f"   a11y 扣分:   -{result['breakdown']['a11y_issues']}")
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
