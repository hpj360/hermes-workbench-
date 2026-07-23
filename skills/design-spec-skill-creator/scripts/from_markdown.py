#!/usr/bin/env python3
"""
从本地 Markdown 设计规范生成 Skill

支持 4 大模板：tokens / component / pattern / full

用法：
  python3 from_markdown.py --input design-spec.md --output skills/team-design/ --template tokens
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# ── 内容提取器 ────────────────────────────────────────────────────────

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\b")
SPACING_RE = re.compile(r"(\d+)\s*px", re.IGNORECASE)
COLOR_KEY_VAL_RE = re.compile(r"(?:color|background|border-color|fill|stroke)\s*[:=]\s*([#0-9A-Fa-f]+|rgb[a]?\([^)]+\)|hsla?\([^)]+\)|[a-z]+)")
FONT_FAMILY_RE = re.compile(r"font-family\s*[:=]\s*[`'\"]?([^`'\"\n;]+)", re.IGNORECASE)
FONT_SIZE_RE = re.compile(r"font-size\s*[:=]\s*[`'\"]?(\d+)\s*px", re.IGNORECASE)


def _extract_section(md_content: str, section_name: str) -> str:
    """提取 ## section_name 下的内容。"""
    pattern = re.compile(rf"^##\s+{re.escape(section_name)}\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(md_content)
    return match.group(1).strip() if match else ""


def _extract_subsection(md_content: str, subsection_name: str) -> str:
    """提取 ### subsection_name 下的内容。"""
    pattern = re.compile(rf"^###\s+{re.escape(subsection_name)}\s*$(.*?)(?=^###\s|^##\s|\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(md_content)
    return match.group(1).strip() if match else ""


def _extract_tokens(md_content: str) -> dict:
    """从 Markdown 提取所有 token。"""
    tokens = {
        "colors": {},
        "typography": {"fontFamily": {}, "fontSize": {}, "fontWeight": {}, "lineHeight": {}},
        "spacing": {},
        "radius": {},
    }

    # 颜色
    colors_section = _extract_section(md_content, "颜色")
    if not colors_section:
        colors_section = _extract_section(md_content, "Colors")
    for match in HEX_RE.finditer(colors_section):
        tokens["colors"][f"color-{len(tokens['colors'])+1}"] = match.group(0).upper()

    # 字体族
    typo_section = _extract_section(md_content, "排版") or _extract_section(md_content, "Typography")
    for i, match in enumerate(FONT_FAMILY_RE.finditer(typo_section)):
        tokens["typography"]["fontFamily"][f"family-{i+1}"] = match.group(1).strip()

    # 字号
    for match in FONT_SIZE_RE.finditer(typo_section):
        tokens["typography"]["fontSize"][f"size-{len(tokens['typography']['fontSize'])+1}"] = int(match.group(1))

    # 间距
    spacing_section = _extract_section(md_content, "间距") or _extract_section(md_content, "Spacing")
    for i, match in enumerate(SPACING_RE.finditer(spacing_section)):
        val = int(match.group(1))
        if val % 4 == 0 and val > 0 and val not in tokens["spacing"].values():
            tokens["spacing"][f"space-{len(tokens['spacing'])+1}"] = val

    return tokens


def _extract_components(md_content: str) -> list[dict]:
    """提取组件清单（## Title 标题下方的属性表）。"""
    components = []
    # 匹配 ## Button/Title/... 风格的标题
    pattern = re.compile(r"^##\s+([A-Z][A-Za-z]+(?:[/-][A-Z][A-Za-z]+)*)\s*$\n(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
    skip_titles = {"颜色", "排版", "间距", "圆角", "阴影", "原则", "反模式",
                   "Colors", "Typography", "Spacing", "Radius", "Effects",
                   "Principles", "Anti-patterns", "Patterns", "Components"}
    for match in pattern.finditer(md_content):
        name = match.group(1).strip()
        if name in skip_titles:
            continue
        body = match.group(2)
        # 提取属性行
        props = []
        for line in body.split("\n"):
            line = line.strip()
            if line.startswith("|") and "---" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts and parts[0] != "属性" and parts[0] != "Property":
                    props.append({"name": parts[0], "type": parts[1] if len(parts) > 1 else "any", "default": parts[2] if len(parts) > 2 else ""})
        if props:
            components.append({"name": name, "props": props})
    return components


def _extract_patterns(md_content: str) -> list[str]:
    """提取设计模式（### 模式：xxx 章节）。"""
    patterns = []
    pattern_re = re.compile(r"^###\s+(?:模式|Pattern)[：:](.*?)(?=^###\s|^##\s|\Z)", re.MULTILINE | re.DOTALL)
    for match in pattern_re.finditer(md_content):
        patterns.append(match.group(1).strip().split("\n")[0])
    return patterns


def _extract_principles(md_content: str) -> list[str]:
    """提取设计原则（## 原则 / ## 反模式 下的列表）。"""
    principles = []
    for section in ("原则", "Principles", "反模式", "Anti-patterns"):
        body = _extract_section(md_content, section)
        for line in body.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                principles.append(line[2:])
    return principles


# ── Skill 生成器 ──────────────────────────────────────────────────────

def _generate_meta(name: str, description: str) -> dict:
    return {
        "name": name,
        "version": "0.1.0",
        "description": description,
        "author": "Generated by design-spec-skill-creator",
        "license": "Apache-2.0",
        "category": "design",
        "generated_from": "markdown",
    }


def _render_tokens_skill(name: str, team: str, tokens: dict, description: str) -> str:
    """生成 tokens 模板的 SKILL.md。"""
    return f"""---
name: {name}
description: {description}
license: Apache-2.0
---

# {team} 设计 Token 规范

由 `design-spec-skill-creator` 自动生成。

## 颜色

{len(tokens.get('colors', {}))} 种颜色已提取到 `tokens/colors.json`。

## 排版

{len(tokens.get('typography', {}).get('fontFamily', {}))} 个字体族，{len(tokens.get('typography', {}).get('fontSize', {}))} 个字号。

## 间距

{len(tokens.get('spacing', {}))} 个间距值（4 栅格）。

## 基础用法

```bash
# 生成 CSS
python3 scripts/generate_css.py --input tokens/ --output dist/tokens.css
```

## 触发场景

- "用项目主色"
- "按设计系统来"
- "改 UI 但没指定颜色"
"""


def _render_component_skill(name: str, team: str, components: list[dict], description: str) -> str:
    """生成 component 模板的 SKILL.md。"""
    comp_table = "\n".join(
        f"| {c['name']} | {len(c['props'])} |" for c in components
    )
    return f"""---
name: {name}
description: {description}
license: Apache-2.0
---

# {team} 组件库规范

由 `design-spec-skill-creator` 自动生成。

## 组件清单

| 组件 | props 数 |
|---|---|
{comp_table}

## 详细文档

见 `references/components.md`（包含每个组件的 props + 例子）。

## 触发场景

- "用 {team} 组件库的 Button"
- "{team} 组件怎么用"
"""


def _render_pattern_skill(name: str, team: str, patterns: list[str], description: str) -> str:
    """生成 pattern 模板的 SKILL.md。"""
    pattern_list = "\n".join(f"- {p}" for p in patterns)
    return f"""---
name: {name}
description: {description}
license: Apache-2.0
---

# {team} 设计模式

由 `design-spec-skill-creator` 自动生成。

## 已提取模式

{pattern_list}

## 详细文档

见 `references/patterns.md`。

## 触发场景

- "{team} 推荐怎么做"
- "{team} 设计模式"
"""


def _render_full_skill(name: str, team: str, all_data: dict, description: str) -> str:
    """生成 full 模板的 SKILL.md。"""
    return f"""---
name: {name}
description: {description}
license: Apache-2.0
---

# {team} 设计系统

由 `design-spec-skill-creator` 自动生成。

## Tokens

{len(all_data['tokens'].get('colors', {}))} 颜色 / {len(all_data['tokens'].get('spacing', {}))} 间距 / {len(all_data['tokens'].get('typography', {}).get('fontSize', {}))} 字号

## 组件

{len(all_data['components'])} 个组件已提取

## 模式

{len(all_data['patterns'])} 个模式已提取

## 原则

{len(all_data['principles'])} 条原则/反模式已提取

## 详细文档

- `tokens/`：所有设计 token
- `references/components.md`：组件详情
- `references/patterns.md`：设计模式
- `references/principles.md`：原则与反模式

## 触发场景

- "按 {team} 设计系统来"
- "用 {team} 的设计规范"
"""


# ── 入口 ──────────────────────────────────────────────────────────────

def generate(input_md: str, output_dir: str, template: str, name: str, team: str) -> dict:
    """主入口：从 Markdown 生成 Skill。"""
    md_path = Path(input_md)
    if not md_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_md}")

    md_content = md_path.read_text(encoding="utf-8")

    # 提取
    tokens = _extract_tokens(md_content)
    components = _extract_components(md_content)
    patterns = _extract_patterns(md_content)
    principles = _extract_principles(md_content)

    description = f"{team} 设计规范自动生成的 Skill"

    # 创建目录结构
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "references").mkdir(exist_ok=True)
    (out / "tokens").mkdir(exist_ok=True)
    (out / "scripts").mkdir(exist_ok=True)

    # 渲染
    if template == "tokens":
        skill_md = _render_tokens_skill(name, team, tokens, description)
    elif template == "component":
        skill_md = _render_component_skill(name, team, components, description)
    elif template == "pattern":
        skill_md = _render_pattern_skill(name, team, patterns, description)
    elif template == "full":
        skill_md = _render_full_skill(
            name, team,
            {"tokens": tokens, "components": components, "patterns": patterns, "principles": principles},
            description,
        )
    else:
        raise ValueError(f"未知模板: {template}")

    # 写入
    (out / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (out / "_meta.json").write_text(
        json.dumps(_generate_meta(name, description), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if tokens.get("colors"):
        (out / "tokens" / "colors.json").write_text(
            json.dumps(tokens["colors"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if tokens.get("spacing"):
        (out / "tokens" / "spacing.json").write_text(
            json.dumps(tokens["spacing"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if components:
        comp_md = "# 组件清单\n\n"
        for c in components:
            comp_md += f"## {c['name']}\n\n"
            comp_md += "| 属性 | 类型 | 默认 |\n|---|---|---|\n"
            for p in c["props"]:
                comp_md += f"| {p['name']} | {p['type']} | {p['default']} |\n"
            comp_md += "\n"
        (out / "references" / "components.md").write_text(comp_md, encoding="utf-8")
    if patterns:
        pat_md = "# 设计模式\n\n" + "\n".join(f"## {p}\n\n" for p in patterns)
        (out / "references" / "patterns.md").write_text(pat_md, encoding="utf-8")
    if principles:
        prin_md = "# 设计原则 / 反模式\n\n" + "\n".join(f"- {p}" for p in principles)
        (out / "references" / "principles.md").write_text(prin_md, encoding="utf-8")

    return {
        "skill_name": name,
        "team": team,
        "template": template,
        "output_dir": str(out),
        "extracted": {
            "colors": len(tokens.get("colors", {})),
            "spacing": len(tokens.get("spacing", {})),
            "components": len(components),
            "patterns": len(patterns),
            "principles": len(principles),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="从 Markdown 设计规范生成 Skill")
    parser.add_argument("--input", required=True, help="输入 Markdown 文件")
    parser.add_argument("--output", required=True, help="输出 Skill 目录")
    parser.add_argument("--template", default="full", choices=["tokens", "component", "pattern", "full"])
    parser.add_argument("--name", required=True, help="Skill 名（kebab-case）")
    parser.add_argument("--team", required=True, help="团队名（人类可读）")
    args = parser.parse_args()

    result = generate(args.input, args.output, args.template, args.name, args.team)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
