# Tokens 模板

适用于：以设计 token（颜色/字体/间距等）为主的设计规范。

```markdown
---
name: {team-name}-design-tokens
description: {team} 设计 token 规范。当用户在前端任务中需要选择颜色/字体/间距等设计值时使用此 skill。覆盖 {N} 个 token 类别：colors/typography/spacing/radius/effects。
license: Apache-2.0
---

# {Team} 设计 Token 规范

## Token 类别

| 类别 | 文件 | 字段 | 说明 |
|---|---|---|---|
{descriptions}

## 颜色 ({N} 种)
{color_table_or_swatch}

## 排版
{typography_table}

## 间距
{spacing_table}

## 圆角
{radius_table}

## 阴影
{shadow_table}

## 基础用法

```bash
# 读取所有 token
python3 scripts/generate_css.py --input tokens/ --output dist/tokens.css
```

## 触发场景

- "{trigger_1}"
- "{trigger_2}"
- "{trigger_3}"
```

## 字段说明

- `{team-name}`：团队名（小写连字符）
- `{team}`：团队名（人类可读）
- `{N}`：token 数量
- `{descriptions}`：每个 token 类别一行 markdown 表格
- `{color_table_or_swatch}`：颜色表或 swatch 图
- `{*_table}`：markdown 表格

## 必要文件

- `SKILL.md`（用本模板填充）
- `_meta.json`
- `tokens/colors.json`
- `tokens/typography.json`
- `tokens/spacing.json`
- `tokens/radius.json`
- `tokens/effects.json`
- `tokens/breakpoints.json`
- `scripts/generate_css.py`（来自 ui-design-system skill）
