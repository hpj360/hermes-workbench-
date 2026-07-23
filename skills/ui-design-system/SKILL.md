---
name: ui-design-system
description: |
  Design Token 与设计系统基础。提供 6 类 token 校验、生成 CSS/Tailwind/Swift 多端
  产物、命名一致性审计、最佳实践扫描。
  Use when: 启动新项目的 design token；把 design tokens 同步到 web/iOS/Android；
  检查 token 命名是否符合规范（kebab-case + 语义化）；需要把 Figma 提取的 JSON 转
  为代码可消费的格式。
  Not for: 直接生成 React/Vue 组件（用 storybook-chromatic）；选型组件库（用
  component-library-selector）。
---

# UI Design System

> **核心思想**：把 design token 沉淀为一份"单一事实源"，自动派生 CSS / Tailwind /
> Swift 等多端产物，让 web/iOS/Android 共享同一套设计语义。

---

## 1. 6 类 Token 体系

| 类别 | 字段 | 示例 | 规范 |
|------|------|------|------|
| Color | color.primary, color.surface | `#3B82F6`, `rgba(0,0,0,0.5)` | 16/24-bit HEX 或 RGBA；禁止命名色 |
| Typography | font.family, font.size, font.weight | `Inter`, `14px`, `500` | family 用 -family 后缀 |
| Spacing | space.1, space.2 | `4px`, `8px`, `12px` | 4/8 基数制 |
| Radius | radius.sm, radius.md | `4px`, `8px`, `12px` | -sm/-md/-lg/-xl |
| Shadow | shadow.sm, shadow.md | `0 1px 2px rgba(0,0,0,0.1)` | 最多 2 层 |
| Motion | duration.fast, easing.default | `150ms`, `cubic-bezier(0.4,0,0.2,1)` | ms 单位 |

## 2. 目录结构

```
ui-design-system/
├── SKILL.md
├── _meta.json
├── references/
│   └── token-spec.md          # Token 详细规范
├── tokens/
│   ├── tokens.base.json       # 原始 token（canonical source）
│   ├── tokens.alias.json      # 语义化别名（color.primary → color.blue.500）
│   └── tokens.schema.json     # JSON Schema 校验
├── scripts/
│   ├── validate.py            # 校验 token 格式 + 命名 + 对比度
│   ├── generate_css.py        # → CSS variables
│   ├── generate_tailwind.py   # → tailwind.config.js
│   ├── generate_swift.py      # → Swift UIColor/UIFont
│   ├── generate_android.py    # → Android colors.xml/dimens.xml
│   └── audit.py               # 命名一致性 + AI 味反模式扫描
└── data/
    └── sample-tokens.json
```

## 3. 快速开始

```bash
# 1. 校验
python3 scripts/validate.py --tokens tokens/tokens.base.json

# 2. 生成多端
python3 scripts/generate_css.py --tokens tokens/tokens.base.json --output dist/tokens.css
python3 scripts/generate_tailwind.py --tokens tokens/tokens.base.json --output tailwind.config.js
python3 scripts/generate_swift.py --tokens tokens/tokens.base.json --output dist/Tokens.swift

# 3. 审计
python3 scripts/audit.py --tokens tokens/tokens.base.json --strict
```

## 4. 设计原则

- **单一事实源**：tokens.base.json 是 canonical，其他都是从它派生
- **可机器校验**：所有规则都用代码 enforce，不靠 PR review
- **多端一致性**：同一份 token，5 端产物必须语义一致

## 5. 命名规则

- 全部 kebab-case 或 dot.case（推荐 dot.case，与 Style Dictionary 对齐）
- 颜色按色相分组：`color.blue.500`、`color.gray.100`
- 语义化别名独立命名空间：`color.primary`、`color.surface`
- 字号用 t-shirt 命名：`font.size.xs/sm/md/lg/xl/2xl`
