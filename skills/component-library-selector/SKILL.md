---
name: component-library-selector
description: |
  组件库选型决策助手。覆盖 13+ 主流 React/Vue 组件库（shadcn/ui、Radix、
  Ant Design、Mantine、Chakra、Material UI、Naive UI、Element Plus、Arco Design、
  Semi Design、Tailwind UI、Park UI、HeroUI），按 8 个维度加权评分，给出推荐。
  Use when: 新项目选型；为团队选标准组件库；评估从 A 库迁移到 B 库；为 AI 编码
  Agent 选择最易控制的 UI 框架。
  Not for: 写组件库本身（用 storybook-chromatic）；比较 CSS 框架 vs 组件库
  （用 ui-design-system）。
---

# Component Library Selector

> **核心思想**：把"组件库选型"从主观争论变成 8 维度加权评分，给出可解释的推荐。

---

## 1. 8 个评分维度

| # | 维度 | 权重 | 说明 |
|---|------|------|------|
| 1 | Bundle size | 15% | gzip 后体积（KB） |
| 2 | Customization | 20% | 主题/Token 可覆盖程度 |
| 3 | TypeScript | 10% | TS 支持成熟度 |
| 4 | Accessibility | 15% | WCAG 2.1 AA 默认达标率 |
| 5 | Component coverage | 10% | 60+ 必备组件覆盖率 |
| 6 | Community | 10% | GitHub stars / npm 周下载 |
| 7 | Documentation | 10% | 文档完整度 + 中文支持 |
| 8 | AI-friendly | 10% | 单一来源、Token 化、源码可读 |

## 2. 13 个候选库

| 库 | 类型 | 适用场景 |
|----|------|----------|
| shadcn/ui | Headless + Tailwind | 现代 web、AI 友好（推荐） |
| Radix UI | Headless | 完全自定义设计 |
| Ant Design | Full | 企业中后台、表格密集 |
| Material UI (MUI) | Full | Material 风格、跨平台 |
| Mantine | Full | 现代 + 丰富 hooks |
| Chakra UI | Full | 简单上手 |
| HeroUI (NextUI) | Full | 美观默认样式 |
| Naive UI | Full | Vue 3 + TS 优秀 |
| Element Plus | Full | Vue 3 + 国内生态 |
| Arco Design | Full | 字节系、ToB |
| Semi Design | Full | 抖音系、设计感强 |
| Tailwind UI | Templates | 商业、高质模板 |
| Park UI | Headless | Panda CSS + Ark UI |

## 3. 目录结构

```
component-library-selector/
├── SKILL.md
├── _meta.json
├── references/
│   ├── decision-tree.md          # 选型决策树
│   ├── ai-coding-tips.md         # AI 编码最佳搭配
│   └── migration-guide.md        # 迁移指南索引
├── scripts/
│   ├── select.py                 # 加权评分主入口
│   └── compare.py                # 库与库对比
└── data/
    └── libraries.json            # 13 库详细评分
```

## 4. 快速开始

```bash
# 1. 单场景推荐
python3 scripts/select.py --scenario "modern-web" --top 3

# 2. 对比两个库
python3 scripts/compare.py --a shadcn-ui --b ant-design

# 3. 全列表
python3 scripts/select.py --scenario any --top 13
```

## 5. 选型决策树

```
是否需要完全自定义视觉？
├─ 是 → shadcn/ui（Tailwind + Radix）
└─ 否 → 需要企业/中后台？
    ├─ 是 → 国际化？中文为主？
    │   ├─ 是 → Arco Design / Ant Design
    │   └─ 否 → MUI / Mantine
    └─ 否 → 性能优先？Vue or React？
        ├─ Vue 3 → Naive UI / Element Plus
        └─ React → HeroUI / Mantine
```

## 6. AI 编码友好度（新增维度）

shadcn/ui 在 AI 编码场景下的优势：
- 组件源码复制到项目（不是 npm 黑盒）
- Tailwind class 易于 LLM 理解
- Radix Primitives 提供 a11y 默认值
- 设计 token 单一来源
