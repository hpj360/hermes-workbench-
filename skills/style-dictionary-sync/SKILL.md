---
name: style-dictionary-sync
description: |
  Style Dictionary 风格的多端 token 同步器。把一份 DTCG 标准 JSON 同步为
  CSS / SCSS / JS / TS / Swift / Android / Flutter / Compose 8 端产物。
  轻量自研（不依赖 npm），CI 友好。
  Use when: 一份 design tokens 多端共享；建立 design system 流水线；把现有
  Figma token JSON 自动同步到代码；为 monorepo 中多个前端项目统一 token 源。
  Not for: 编辑 token 内容（用 ui-design-system）；跑 Style Dictionary 本身
  （如已用 npm，本 skill 是其 Python 等价物）。
---

# Style Dictionary Sync

> **核心思想**：DTCG（Design Token Community Group）格式是事实标准，本 skill 用
> Python 实现一个轻量、零依赖的多端同步器，覆盖最常用的 8 端产物。

---

## 1. 8 端产物

| 端 | 格式 | 文件 |
|----|------|------|
| Web | CSS variables | `tokens.css` |
| Web | SCSS variables | `tokens.scss` |
| Web | JS object | `tokens.js` |
| Web | TS object | `tokens.ts` |
| iOS | Swift | `Tokens.swift` |
| Android | XML | `colors.xml`/`dimens.xml` |
| Flutter | Dart | `tokens.dart` |
| Compose | Kotlin | `Tokens.kt` |

## 2. 目录结构

```
style-dictionary-sync/
├── SKILL.md
├── _meta.json
├── references/
│   └── dtcg-spec.md             # DTCG 格式说明
├── examples/
│   ├── tokens.dtcg.json         # 示例 DTCG 格式
│   └── config.json              # 同步配置示例
└── scripts/
    ├── sync.py                  # 主入口
    ├── resolve.py               # 别名解析 {color.primary}
    └── formatters/              # 8 端格式化器
        ├── css.py
        ├── scss.py
        ├── js.py
        ├── ts.py
        ├── swift.py
        ├── android.py
        ├── flutter.py
        └── compose.py
```

## 3. 快速开始

```bash
# 同步所有端（默认配置）
python3 scripts/sync.py --input tokens.dtcg.json --output-dir ./dist

# 仅同步 web 端
python3 scripts/sync.py --input tokens.dtcg.json --output-dir ./dist --platforms web

# 同步 CSS + Swift
python3 scripts/sync.py --input tokens.dtcg.json --output-dir ./dist --platforms css,swift
```

## 4. DTCG 格式示例

```json
{
  "color": {
    "primary": { "$value": "#3B82F6", "$type": "color" },
    "surface": { "$value": "#FFFFFF", "$type": "color" }
  },
  "font": {
    "size": {
      "body": { "$value": "16px", "$type": "dimension" }
    }
  }
}
```

## 5. 与 ui-design-system 关系

- ui-design-system：原始 token 定义 + 校验
- style-dictionary-sync：DTCG 标准 + 多端派生

可以组合使用：ui-design-system 输出 → 转换为 DTCG → sync 多端。
