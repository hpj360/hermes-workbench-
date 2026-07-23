---
name: ui-review-checklist
description: |
  UI 评审检查清单与反模式扫描器。覆盖 13 类 AI 味反模式 + 13 项可访问性 +
  8 项性能 + 6 项一致性。提供 Python 扫描脚本和 Markdown 评审清单。
  Use when: 设计稿/前端代码评审；提交 PR 前自查；新项目视觉基线检查；判断某 UI
  是否"看起来太 AI"。
  Not for: 自动修复反模式（只检测不修复）；具体设计语言（Liquid Glass/Material
  各自独立 skill）。
---

# UI Review Checklist

> **核心思想**：把"好 UI 的判定标准"沉淀为可机器执行的检查清单，让 AI 生成的 UI
> 也能通过客观度量评估质量。

---

## 1. 13 类 AI 味反模式

| # | 反模式 | 检测方法 | 替代方案 |
|---|--------|----------|----------|
| 1 | Inter 字体 | grep `font-family.*Inter` | 系统字体或定制字体 |
| 2 | 紫蓝渐变 | 检测 #6xxxFF-#8xxxFF 范围 | 真实业务色 |
| 3 | 卡片化布局滥用 | 统计每屏卡片数 > 8 | 列表/网格混排 |
| 4 | emoji 当图标 | 检测 ❤🚀💡 | 真实 icon 库（Lucide/Phosphor） |
| 5 | 占位图（unsplash/picsum） | 检测 `picsum.photos` URL | 真实素材 |
| 6 | 统一圆角 8/12px | 所有 border-radius 同值 | 4/8/12/16 多级圆角 |
| 7 | 居中对称过度 | flex/grid 全部 center/space-around | 不对称布局 |
| 8 | 12 列栅格死板 | 仅用 12 列 | 12/16/24 列混用 |
| 9 | 模板阴影 | box-shadow 0 4px 6px rgb(0 0 0 / 0.1) | 物理性阴影 |
| 10 | 默认动效 | transition 200ms ease 一刀切 | 距离+权重动效 |
| 11 | 单一字号 | 全文 text-base 16px | 12-32 多级 |
| 12 | 模板按钮 | 所有按钮同色同尺寸 | 4 种 button variant |
| 13 | 纯灰配色 | 仅有 gray 色相 | 中性色 + 强调色 |

## 2. 13 项可访问性检查

1. 文本对比度 >= 4.5:1
2. 大文本对比度 >= 3:1
3. 交互元素 >= 44×44 px
4. 焦点环可见
5. 颜色不是唯一信息载体
6. 表单有 label
7. 错误消息明确
8. alt 属性
9. 语义化标签（h1-h6、nav、main）
10. 键盘可达
11. 跳过导航
12. ARIA 正确
13. prefers-reduced-motion 支持

## 3. 8 项性能

1. LCP < 2.5s
2. FID < 100ms
3. CLS < 0.1
4. 图片懒加载
5. CSS 关键路径 < 14KB
6. 无 layout shift
7. 字体子集化
8. backdrop-filter 限制数量

## 4. 目录结构

```
ui-review-checklist/
├── SKILL.md
├── _meta.json
├── references/
│   ├── anti-patterns.md        # 13 类反模式详解
│   ├── a11y-checklist.md       # 13 项 a11y
│   └── perf-checklist.md       # 8 项性能
├── scripts/
│   ├── scan.py                 # 代码扫描器
│   ├── score.py                # 综合评分
│   └── report.py               # 生成 Markdown 报告
└── data/
    └── patterns.json           # 反模式正则库
```

## 5. 快速开始

```bash
# 1. 扫描代码
python3 scripts/scan.py --target ./src --patterns data/patterns.json --output scan.json

# 2. 评分
python3 scripts/score.py --scan-result scan.json

# 3. 报告
python3 scripts/report.py --scan-result scan.json --output report.md
```

## 6. 评分维度

- 反模式（-30 分上限）
- 可访问性（-25 分上限）
- 性能（-20 分上限）
- 一致性（-15 分上限）
- 设计语言（-10 分上限）

起始分 100，每个反模式扣分。
