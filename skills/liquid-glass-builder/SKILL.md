---
name: liquid-glass-builder
description: |
  Apple WWDC 2025 Liquid Glass 设计语言实施器。生成 Web 端（CSS backdrop-filter +
  React 组件）和 iOS SwiftUI（GlassEffectContainer）双端的玻璃化 UI 组件。
  Use when: 构建需要质感/高级感/差异化视觉的 web/iOS 界面；现有 UI 过于扁平；
  需要将 Web 玻璃化组件映射到 iOS 原生；参考 Apple Vision Pro 风格做透明度叠加。
  Not for: 极简风（Material You/Flat Design）；性能敏感场景（避免 backdrop-filter
  滥用）；对老浏览器/老设备的支持（fallback 需另行设计）。
---

# Liquid Glass Builder

> **核心思想**：把 Apple WWDC 2025 发布的 Liquid Glass 设计语言封装为可复用 skill，
> 让 Web/iOS 双端都能以"玻璃化"质感表达 UI 差异化。

---

## 1. 设计语言要点

| 维度 | 规则 | 反例 |
|------|------|------|
| 透明度 | 背景色用 rgba，alpha 0.4-0.8 | 实色 + 高斯模糊贴图 |
| 模糊半径 | 12-40px，过大反而发灰 | backdrop-filter: blur(100px) |
| 边框 | 1px 白色 alpha 0.2-0.3 内描边 | 2-3px 实色边框 |
| 高光 | 顶部 1px 白色 alpha 0.5 渐变 | 多重 drop-shadow |
| 阴影 | 1 层柔和 shadow + 1 层 specular | 4-5 层叠加 |
| 颜色 | 中性灰/白为主，色相不超过 2 种 | 紫蓝渐变 + 玻璃 |
| 层级 | 玻璃面之上只放 1-2 种信息 | 玻璃 + 卡片 + 弹窗 + 抽屉 |

**绝对禁忌**：
- ❌ Inter 字体 + 紫蓝渐变 + 玻璃（AI 味三件套）
- ❌ 全屏玻璃（性能差、阅读性差）
- ❌ 玻璃 + 玻璃 + 玻璃（看不清层级）

## 2. 目录结构

```
liquid-glass-builder/
├── SKILL.md                  # 本文件
├── _meta.json                # 元数据
├── references/
│   ├── design-language.md    # 详细设计语言规范
│   ├── components.md         # 玻璃组件目录与用法
│   └── patterns.md           # 典型组合模式（导航/卡片/Modal）
├── web/
│   ├── liquid-glass.css      # CSS 变量 + 工具类
│   ├── GlassPanel.tsx        # 通用玻璃面板
│   └── useGlass.ts           # React hook（动态 blur/alpha）
├── ios/
│   └── LiquidGlassView.swift # SwiftUI 实现
└── scripts/
    └── web_to_ios.py         # Web 组件 → SwiftUI 草稿转换器
```

## 3. 快速开始

### 3.1 Web 端

```tsx
import { GlassPanel } from './GlassPanel';
import './liquid-glass.css';

<GlassPanel blur={24} alpha={0.6} border highlight>
  <h2>Apple-style Glass</h2>
  <p>通透、立体、有质感</p>
</GlassPanel>
```

### 3.2 iOS 端

```swift
import SwiftUI

LiquidGlassView(blur: 24, alpha: 0.6) {
    VStack {
        Text("Apple-style Glass")
        Text("通透、立体、有质感")
    }
}
```

## 4. 设计原则（与 Hermes working principles 对齐）

1. **从约束出发**：backdrop-filter 性能预算 vs 视觉品质，找到平衡点
2. **避免 AI 味**：禁止 Inter+渐变+玻璃三件套；坚持材质物理性
3. **复杂任务后多 Agent 审查**：玻璃化设计上线前必须有性能/无障碍/可读性三方面审查

## 5. 不做什么

- 不替代 design-system（本 skill 是 design-system 的视觉材质层）
- 不做 3D 倾斜/视差（Liquid Glass 是静态材质，非动态视差）
- 不在弱光环境下默认亮玻璃（自动降级为半实色）
