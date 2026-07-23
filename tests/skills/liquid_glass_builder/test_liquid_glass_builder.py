"""Tests for liquid-glass-builder Skill"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent.parent / "skills" / "liquid-glass-builder"
SCRIPTS = SKILL_DIR / "scripts"

sys.path.insert(0, str(SCRIPTS))


class TestWebToIos:
    """测试 Web → iOS SwiftUI 转换器"""

    def test_parse_props(self):
        from web_to_ios import parse_props
        props = parse_props("blur=24,alpha=0.6,highlight=true,dispersion=false")
        assert props["blur"] == 24
        assert props["alpha"] == 0.6
        assert props["highlight"] is True
        assert props["dispersion"] is False

    def test_generate_swiftui(self):
        from web_to_ios import generate_swiftui
        code = generate_swiftui({"blur": 24, "alpha": 0.6, "highlight": True}, "Text(\"Hi\")")
        assert "LiquidGlassView(" in code
        assert "blur: 24" in code
        assert "alpha: 0.6" in code
        assert "@available(iOS 17.0" in code

    def test_generate_with_dispersion(self):
        from web_to_ios import generate_swiftui
        code = generate_swiftui({"blur": 40, "alpha": 0.7, "dispersion": True})
        assert "dispersion: true" in code

    def test_cli_basic(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "web_to_ios.py"),
             "--props", "blur=24,alpha=0.6,highlight=true",
             "--content", 'VStack { Text("Hi") }',
             "--output", str(tmp_path / "Generated.swift")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (tmp_path / "Generated.swift").exists()


class TestFiles:
    """测试 skill 关键文件存在"""

    def test_css_file_exists(self):
        assert (SKILL_DIR / "web" / "liquid-glass.css").exists()

    def test_tsx_file_exists(self):
        assert (SKILL_DIR / "web" / "GlassPanel.tsx").exists()

    def test_swift_file_exists(self):
        assert (SKILL_DIR / "ios" / "LiquidGlassView.swift").exists()

    def test_references_exist(self):
        for ref in ["design-language.md", "components.md", "patterns.md"]:
            assert (SKILL_DIR / "references" / ref).exists()
