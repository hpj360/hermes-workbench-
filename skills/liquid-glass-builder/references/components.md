# Liquid Glass 组件目录

## Web 端组件

### GlassPanel
**用途**：通用玻璃容器
**Props**：
- `blur?: number` — 模糊半径（默认 24）
- `alpha?: number` — 背景透明度（默认 0.6）
- `border?: boolean` — 是否显示 1px 高光边框（默认 true）
- `highlight?: boolean` — 顶部高光（默认 false）
- `variant?: 'light' | 'dark' | 'auto'` — 主题（默认 auto）
- `as?: keyof JSX.IntrinsicElements` — 渲染元素（默认 div）

### GlassButton
**用途**：玻璃质感按钮
**Props**：
- 继承 GlassPanel
- `onClick: () => void`
- `disabled?: boolean`
- `size?: 'sm' | 'md' | 'lg'`

### GlassNavigation
**用途**：顶部/底部导航栏
**特殊**：
- position: sticky
- 仅背景区域应用 backdrop-filter
- 不阻挡背后内容点击

### GlassCard
**用途**：内容卡片
**与 GlassPanel 区别**：
- 更大的 padding (>= 16px)
- 自带阴影
- 默认 highlight=true

## iOS 端组件

### LiquidGlassView
**用途**：通用 SwiftUI 玻璃容器
**API**：
```swift
LiquidGlassView(
    blur: CGFloat = 20,
    alpha: Double = 0.6,
    cornerRadius: CGFloat = 12
) {
    // 子内容
}
```

### LiquidGlassButton
**用途**：玻璃按钮
**特殊**：
- press 状态有 spring 动画
- 默认 tint 跟随 accent color

### LiquidGlassTabBar
**用途**：底部 Tab Bar
**实现要点**：
- 背景用 .ultraThinMaterial（iOS 15+）或 LiquidGlassView（iOS 17+）
- 选中态有 specular highlight
