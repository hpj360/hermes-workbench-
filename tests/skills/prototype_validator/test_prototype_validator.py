"""Tests for prototype-validator Skill"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent.parent / "skills" / "prototype-validator"
SCRIPTS = SKILL_DIR / "scripts"


class TestRunAll:
    """测试一键验证（mock 模式）"""

    def test_run_all_generates_reports(self, tmp_path):
        subprocess.run(
            [sys.executable, str(SCRIPTS / "run_all.py"),
             "--url", "http://example.invalid", "--output-dir", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        # mock 模式下应该能跑完（exit 0 或 1 都可）
        report_files = sorted(tmp_path.glob("*.json"))
        # 至少有 perf + a11y 报告
        assert len(report_files) >= 2, f"expected 2+ reports, got {report_files}"
        assert any("perf" in p.name for p in report_files)
        assert any("a11y" in p.name for p in report_files)

    def test_run_all_score_in_range(self, tmp_path):
        """总分应在 0-100 之间"""
        subprocess.run(
            [sys.executable, str(SCRIPTS / "run_all.py"),
             "--url", "http://mock.test", "--output-dir", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        perf_report = tmp_path / "perf.json"
        if perf_report.exists():
            import json
            data = json.loads(perf_report.read_text())
            # 兼容两种结构：top-level score 或 categories.performance
            score = data.get("score") or data.get("categories", {}).get("performance")
            assert score is not None, f"perf score not found in: {list(data.keys())}"
            assert 0 <= score <= 100, f"score out of range: {score}"
