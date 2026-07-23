"""Tests for design-spec-skill-creator Skill"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent.parent / "skills" / "design-spec-skill-creator"
SCRIPTS = SKILL_DIR / "scripts"

sys.path.insert(0, str(SCRIPTS))


class TestPackageSkill:
    """测试 Skill 包验证器"""

    def test_validate_valid_skill(self, tmp_path):
        """合法 skill 目录应通过"""
        skill_dir = tmp_path / "good-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: good-skill\ndescription: A good skill for testing purposes and unit tests\n---\n\n# Good Skill\n"
        )
        (skill_dir / "_meta.json").write_text('{"name": "good-skill", "version": "0.1.0"}')

        from package_skill import validate
        result = validate(str(skill_dir))
        # result keys: info, issues
        assert "issues" in result
        critical = [i for i in result["issues"] if i.get("severity") == "critical"]
        assert len(critical) == 0, f"unexpected critical: {critical}"

    def test_validate_missing_skill_md(self, tmp_path):
        """缺少 SKILL.md 应有 critical issue"""
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "_meta.json").write_text('{"name": "x"}')
        from package_skill import validate
        result = validate(str(skill_dir))
        msgs = [i["message"] for i in result["issues"]]
        assert any("SKILL.md" in m for m in msgs)

    def test_validate_missing_meta(self, tmp_path):
        """缺少 _meta.json 应有 critical issue"""
        skill_dir = tmp_path / "bad-skill2"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: x\ndescription: A valid description with enough length\n---\n")
        from package_skill import validate
        result = validate(str(skill_dir))
        msgs = [i["message"] for i in result["issues"]]
        assert any("_meta.json" in m for m in msgs)

    def test_validate_frontmatter_validation(self, tmp_path):
        """SKILL.md 无 frontmatter 应有 critical"""
        skill_dir = tmp_path / "no-frontmatter"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Just a title, no frontmatter\n")
        (skill_dir / "_meta.json").write_text('{}')
        from package_skill import validate
        result = validate(str(skill_dir))
        msgs = [i["message"] for i in result["issues"]]
        assert any("frontmatter" in m.lower() for m in msgs)


class TestFromMarkdown:
    """测试 Markdown → tokens 提取"""

    def test_extract_section(self):
        from from_markdown import _extract_section
        md = "# Title\n\n## Tokens\n\ncontent\n\n## Components\n\nstuff"
        section = _extract_section(md, "Tokens")
        assert "content" in section

    def test_extract_section_missing(self):
        from from_markdown import _extract_section
        md = "# Title\n\nno tokens section"
        section = _extract_section(md, "Tokens")
        # 不存在应返回空
        assert section == ""

    def test_extract_principles(self):
        from from_markdown import _extract_principles
        md = """
## Principles

- 始终从用户价值出发
- 保持代码简洁
- 测试驱动
"""
        principles = _extract_principles(md)
        assert len(principles) >= 1
        assert any("用户价值" in p for p in principles)
