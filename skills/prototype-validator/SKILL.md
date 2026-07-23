---
name: prototype-validator
description: 用 Playwright + axe-core 自动验证前端原型（无障碍 / 视觉回归 / 性能 / 交互）。生成 0-100 评分 + 详细 diff 报告，问题定位到具体元素。触发场景：用户说"验证原型""a11y 检查""视觉回归""WCAG 合规""性能跑分""上线前 review"。
license: Apache-2.0
---

# 原型验证器（Playwright + axe-core）

自动验证前端原型的 4 大维度，无障碍 / 视觉回归 / 性能 / 交互。

## 4 大维度

| 维度 | 工具 | 检测项 | 评分标准 |
|---|---|---|---|
| **无障碍 (a11y)** | axe-core | WCAG 2.0/2.1/2.2 AA/AAA、ARIA、键盘导航、颜色对比度 | critical=0 才通过 |
| **视觉回归** | Playwright + pixelmatch | 截图差异（baseline vs current） | 差异 < 0.1% 像素 |
| **性能** | Lighthouse | FCP / LCP / CLS / TBT / Speed Index | 性能 ≥ 90 才通过 |
| **交互** | Playwright | 表单提交、按钮点击、路由跳转 | 所有断言通过 |

## 依赖

```bash
pip install playwright axe-core-python
playwright install chromium
```

或 Node.js 版本：
```bash
npm install -D @playwright/test @axe-core/playwright lighthouse
```

## 基础用法

```bash
# 1. 无障碍检查
python3 scripts/run_a11y.py --url https://example.com --level AA

# 2. 视觉回归
python3 scripts/run_visual.py --url https://example.com --baseline baselines/example.png

# 3. 性能跑分
python3 scripts/run_perf.py --url https://example.com

# 4. 交互验证
python3 scripts/run_interaction.py --url https://example.com --script interactions.json

# 5. 一键全跑
python3 scripts/run_all.py --url https://example.com --output report.json
```

## 评分公式

```
总分 = a11y_score × 0.30 + visual_score × 0.20 + perf_score × 0.30 + interaction_score × 0.20

其中：
- a11y_score = 100 - critical*10 - serious*5 - moderate*2
- visual_score = 100 - diff_ratio × 100
- perf_score = Lighthouse performance × 100
- interaction_score = passed/total × 100
```

| 等级 | 分数 | 含义 |
|---|---|---|
| A | 90-100 | 可上线 |
| B | 75-89 | 微调后上线 |
| C | 60-74 | 需修复多处 |
| D | 40-59 | 重大问题 |
| F | 0-39 | 不可上线 |

## 报告输出

`report.json` 包含：
- 总分 + 等级
- 各维度分数
- 问题列表（按 critical/warning/info 分级）
- 截图（baseline vs current）
- 改进建议

`report.html` 可视化报告（截图嵌入 + 问题位置高亮）。

## 工作流

```
开发完成 → git commit
    ↓
PR 触发 CI
    ↓
prototype-validator 全量跑
    ↓
report 存 PR 评论
    ↓
分数 < 75 → 阻塞合并
分数 ≥ 75 → 通过 review
```

## 不适用

- 跨浏览器测试（仅 Chromium）
- 移动端 native（用 Appium）
- 性能压测（用 k6）

## 与其他 skill 配合

| Skill | 关系 |
|---|---|
| `ui-review-checklist` | 静态代码审查，本 skill 运行时验证 |
| `ui-design-system` | 设计 token 正确性由本 skill 验证 |
| `frontend-design` | 美学方向由 review，本 skill 验证合规 |
| `storybook-chromatic` | Storybook 组件视觉回归用 Chromatic |
