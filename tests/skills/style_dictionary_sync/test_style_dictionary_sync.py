"""Tests for style-dictionary-sync Skill"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent.parent / "skills" / "style-dictionary-sync"
SCRIPTS = SKILL_DIR / "scripts"
EXAMPLES = SKILL_DIR / "examples"

sys.path.insert(0, str(SCRIPTS))


class TestResolve:
    def test_flatten_dtcg(self):
        from resolve import flatten_dtcg
        data = {
            "color": {
                "primary": {"$value": "#FFF", "$type": "color"},
                "secondary": {"$value": "{color.primary}", "$type": "color"},
            }
        }
        result = flatten_dtcg(data)
        assert len(result) == 2
        paths = [r[0] for r in result]
        assert "color.primary" in paths

    def test_resolve_aliases(self):
        from resolve import flatten_dtcg, resolve_aliases
        data = {
            "color": {
                "primary": {"$value": "#FFF", "$type": "color"},
                "text": {"$value": "{color.primary}", "$type": "color"},
            }
        }
        tokens = flatten_dtcg(data)
        resolved = resolve_aliases(tokens)
        assert resolved["color.text"] == "#FFF"

    def test_is_color_detection(self):
        from resolve import is_color
        assert is_color("#FFF")
        assert is_color("#FF00FF")
        assert is_color("rgb(0,0,0)")
        assert not is_color("12px")
        assert not is_color("cubic-bezier(0,0,0,0)")


class TestSync:
    def test_sync_all_platforms(self, tmp_path):
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "sync.py"),
             "--input", str(EXAMPLES / "tokens.dtcg.json"),
             "--output-dir", str(tmp_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        # 8 个端产物都应该生成
        expected = ["tokens.css", "tokens.scss", "tokens.js", "tokens.ts",
                    "Tokens.swift", "tokens.xml", "tokens.dart", "Tokens.kt"]
        for fname in expected:
            assert (tmp_path / fname).exists(), f"missing {fname}"

    def test_sync_single_platform(self, tmp_path):
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "sync.py"),
             "--input", str(EXAMPLES / "tokens.dtcg.json"),
             "--output-dir", str(tmp_path),
             "--platforms", "css"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert (tmp_path / "tokens.css").exists()
        assert not (tmp_path / "tokens.js").exists()

    def test_css_output_format(self, tmp_path):
        import subprocess
        subprocess.run(
            [sys.executable, str(SCRIPTS / "sync.py"),
             "--input", str(EXAMPLES / "tokens.dtcg.json"),
             "--output-dir", str(tmp_path),
             "--platforms", "css"],
            capture_output=True, text=True, timeout=30,
        )
        content = (tmp_path / "tokens.css").read_text()
        assert ":root {" in content
        assert "--color-primary" in content

    def test_flutter_output_format(self, tmp_path):
        import subprocess
        subprocess.run(
            [sys.executable, str(SCRIPTS / "sync.py"),
             "--input", str(EXAMPLES / "tokens.dtcg.json"),
             "--output-dir", str(tmp_path),
             "--platforms", "flutter"],
            capture_output=True, text=True, timeout=30,
        )
        content = (tmp_path / "tokens.dart").read_text()
        assert "class AppTokens" in content
        assert "Color(0xFF" in content
