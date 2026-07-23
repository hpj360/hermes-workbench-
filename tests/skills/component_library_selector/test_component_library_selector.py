"""Tests for component-library-selector Skill"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent.parent / "skills" / "component-library-selector"
SCRIPTS = SKILL_DIR / "scripts"


def run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True, text=True, timeout=30,
    )


class TestSelect:
    def test_ai_coding_recommends_shadcn(self):
        result = run_script("select.py", "--scenario", "ai-coding", "--top", "3")
        assert "shadcn/ui" in result.stdout

    def test_modern_web_recommends_shadcn(self):
        result = run_script("select.py", "--scenario", "modern-web", "--top", "3")
        assert "shadcn/ui" in result.stdout

    def test_vue3_recommends_naive_or_element(self):
        result = run_script("select.py", "--scenario", "vue3", "--top", "3")
        # Vue 3 场景下应该返回 Vue 库
        assert "Naive" in result.stdout or "Element" in result.stdout

    def test_top_limit(self):
        result = run_script("select.py", "--scenario", "any", "--top", "1")
        # 只输出 1 个
        assert result.stdout.count("标签:") == 1


class TestCompare:
    def test_compare_shadcn_vs_antd(self):
        result = run_script("compare.py", "--a", "shadcn-ui", "--b", "ant-design")
        assert "shadcn/ui" in result.stdout
        assert "Ant Design" in result.stdout
        assert "推荐" in result.stdout

    def test_compare_invalid_id(self):
        result = run_script("compare.py", "--a", "invalid", "--b", "ant-design")
        assert result.returncode == 1
        # 错误信息可能在 stdout 或 stderr
        combined = result.stdout + result.stderr
        assert "无效" in combined
