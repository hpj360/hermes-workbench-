# Liquid Glass 设计语言详细规范

> 参考：Apple WWDC 2025 主题演讲、Human Interface Guidelines 更新（iOS 26/macOS 26）

## 1. 物理直觉

Liquid Glass 的核心隐喻是**真实的玻璃**：
- 半透明（不是完全透明也不是实色）
- 折射背景（不是简单 blur）
- 边缘高光（光线在边缘散射）
- 顶部受光、底部投影（与光源方向一致）

**与毛玻璃（Frosted Glass）的区别**：
- 毛玻璃：纯 blur + 灰白底
- Liquid Glass：blur + 折射 + specular + chromatic dispersion（边缘有色散）

## 2. 7 项视觉规范

### 2.1 Blur 强度（按场景）

| 场景 | blur 值 | 备注 |
|------|---------|------|
| 工具栏/Tab Bar | 20-30px | 紧贴内容，必须看清 |
| 侧边栏/抽屉 | 30-50px | 远离交互热点 |
| Modal/弹窗 | 40-60px | 隔离感最强 |
| 通知横幅 | 16-24px | 短暂存在，轻量 |
| 卡片悬浮 | 12-20px | 卡片本身有底色，玻璃感弱化 |

### 2.2 透明度（按主题）

| 主题 | alpha（白底） | alpha（暗底） |
|------|---------------|---------------|
| Light | 0.5-0.7 | 0.3-0.5 |
| Dark | 0.2-0.4 | 0.1-0.2 |
| High Contrast | 0.85+ | 0.7+ |

**WCAG 警告**：玻璃背后文本对比度必须 >= 4.5:1。简单测试：在玻璃面板上放 16px 黑字，截图测亮度比。

### 2.3 边框

- 1px 白色 alpha 0.2-0.3（亮主题）
- 1px 黑色 alpha 0.2-0.4（暗主题）
- 永远不描外边阴影代替边框

### 2.4 高光

```css
.glass-highlight {
  background:
    linear-gradient(180deg,
      rgba(255, 255, 255, 0.5) 0%,
      rgba(255, 255, 255, 0) 30%);
  height: 1px;
  position: absolute;
  top: 0; left: 0; right: 0;
}
```

### 2.5 阴影

```css
.glass-shadow {
  box-shadow:
    0 8px 24px rgba(0, 0, 0, 0.12),  /* 主阴影 */
    0 2px 4px rgba(0, 0, 0, 0.08);    /* 接触阴影 */
}
```

不要叠加 3 层以上阴影。

### 2.6 色散（可选）

边缘 1-2px 的彩虹渐变（来自 backdrop-filter: hue-rotate + saturate 配合）。仅限关键 CTA/导航，避免滥用。

```css
.glass-edge-dispersion {
  background:
    linear-gradient(135deg,
      rgba(255, 100, 100, 0.1),
      rgba(100, 255, 100, 0.05),
      rgba(100, 100, 255, 0.1));
}
```

### 2.7 抗锯齿

- border-radius >= 8px（小元素会失真）
- 使用 transform: translateZ(0) 触发 GPU 合成层
- will-change: backdrop-filter 仅在动画期间使用

## 3. 性能预算

| 指标 | 预算 |
|------|------|
| 同时使用 backdrop-filter 的元素数 | <= 3 |
| backdrop-filter 半径之和 | <= 120px |
| 玻璃元素嵌套层数 | <= 2 |
| 动画期间重绘面积 | <= 30% viewport |

**降级策略**：
```css
@supports not (backdrop-filter: blur(10px)) {
  .glass {
    background: rgba(255, 255, 255, 0.85); /* fallback 到实色 */
  }
}
@media (prefers-reduced-motion: reduce) {
  .glass { backdrop-filter: none; }
}
```

## 4. 何时使用 vs 不使用

| 场景 | 推荐 |
|------|------|
| 工具栏、Tab Bar、抽屉 | ✅ 推荐 |
| 主内容卡片 | ⚠️ 谨慎（影响阅读） |
| 大量数据列表 | ❌ 不推荐 |
| 视频/图片上层 | ⚠️ 需配 fallback |
| 暗色主题主背景 | ❌ 容易发灰 |

## 5. 与其他设计语言的关系

| 设计语言 | 关系 |
|----------|------|
| Material Design 3 Expressive | 完全不同的方向（强调形状+色彩） |
| Fluent Design Acrylic | 同源（Microsoft 在 2017 的实现） |
| VisionOS Glass | 直接继承（Liquid Glass 是其 Web 化） |
| Neumorphism | 不兼容（强调内阴影，与玻璃冲突） |
| Glassmorphism（2020 风潮） | 祖先，但更克制 |
