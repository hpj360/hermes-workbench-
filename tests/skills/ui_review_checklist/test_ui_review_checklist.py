"""Tests for ui-review-checklist Skill"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent.parent / "skills" / "ui-review-checklist"
SCRIPTS = SKILL_DIR / "scripts"


def run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True, text=True, timeout=30,
    )


class TestScan:
    def test_scan_detects_inter_font_via_json(self, tmp_path):
        f = tmp_path / "ui.html"
        f.write_text("<html><style>body { font-family: 'Inter', sans-serif; }</style></html>")
        out = tmp_path / "scan.json"
        run_script("scan.py", "--target", str(f), "--output", str(out))
        data = json.loads(out.read_text())
        ids = [x["id"] for x in data["findings"]["anti_patterns"]]
        assert "inter-font" in ids

    def test_scan_detects_picsum_via_json(self, tmp_path):
        f = tmp_path / "ui.html"
        f.write_text('<img src="https://picsum.photos/200">')
        out = tmp_path / "scan.json"
        run_script("scan.py", "--target", str(f), "--output", str(out))
        data = json.loads(out.read_text())
        ids = [x["id"] for x in data["findings"]["anti_patterns"]]
        assert "placeholder-image" in ids

    def test_scan_clean_file_zero_hits(self, tmp_path):
        f = tmp_path / "clean.html"
        f.write_text("<html><body>Hello</body></html>")
        out = tmp_path / "scan.json"
        run_script("scan.py", "--target", str(f), "--output", str(out))
        data = json.loads(out.read_text())
        assert len(data["findings"]["anti_patterns"]) == 0

    def test_scan_summary_in_stdout(self, tmp_path):
        f = tmp_path / "ui.html"
        f.write_text("<html><body>x</body></html>")
        result = run_script("scan.py", "--target", str(f))
        assert "反模式命中: 0" in result.stdout
        assert "a11y 问题:" in result.stdout


class TestScore:
    def test_score_perfect(self, tmp_path):
        scan = {
            "target": "/tmp/x", "files_scanned": 1,
            "findings": {"anti_patterns": [], "a11y_issues": []},
            "summary": {"anti_patterns_count": 0, "a11y_issues_count": 0},
        }
        scan_path = tmp_path / "scan.json"
        scan_path.write_text(json.dumps(scan))
        result = run_script("score.py", "--scan-result", str(scan_path))
        assert result.returncode == 0
        assert "100" in result.stdout
        assert "A" in result.stdout

    def test_score_with_one_high_finding_fails(self, tmp_path):
        """high severity 应该扣够多分让分 < 75 失败"""
        scan = {
            "target": "/tmp/x", "files_scanned": 1,
            "findings": {
                "anti_patterns": [
                    {"id": "inter-font", "severity": "high"},
                    {"id": "placeholder-image", "severity": "high"},
                    {"id": "purple-blue-gradient", "severity": "high"},
                ],
                "a11y_issues": [],
            },
            "summary": {"anti_patterns_count": 3, "a11y_issues_count": 0},
        }
        scan_path = tmp_path / "scan.json"
        scan_path.write_text(json.dumps(scan))
        result = run_script("score.py", "--scan-result", str(scan_path))
        # 3 个 high 应扣分足够多
        assert "反模式扣分" in result.stdout
