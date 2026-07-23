"""Tests for storybook-chromatic Skill"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent.parent / "skills" / "storybook-chromatic"
SCRIPTS = SKILL_DIR / "scripts"
TEMPLATES = SKILL_DIR / "templates"

sys.path.insert(0, str(SCRIPTS))


class TestSyncFigmaToStory:
    """测试 CSF 3.0 story 生成器内部函数"""

    def test_to_pascal_case(self):
        from sync_figma_to_story import _to_pascal_case
        assert _to_pascal_case("Button/Primary") == "ButtonPrimary"
        assert _to_pascal_case("btn-primary") == "BtnPrimary"
        assert _to_pascal_case("simple") == "Simple"

    def test_to_camel_case(self):
        from sync_figma_to_story import _to_camel_case
        assert _to_camel_case("primary") == "primary"
        assert _to_camel_case("Button/Primary") == "buttonPrimary"

    def test_generate_component_stub(self):
        from sync_figma_to_story import generate_component_stub
        out = generate_component_stub("Button", "Primary button")
        assert "export const Button" in out
        assert "React.FC" in out
        assert "variant" in out


class TestTemplates:
    """测试模板文件存在"""

    def test_storybook_config_template(self):
        assert (TEMPLATES / "storybook.config.js").exists()

    def test_chromatic_config_template(self):
        assert (TEMPLATES / "chromatic.config.json").exists()

    def test_storybook_config_has_framework(self):
        content = (TEMPLATES / "storybook.config.js").read_text()
        # 应包含 Storybook 配置核心字段
        assert "stories" in content
        assert "addons" in content
