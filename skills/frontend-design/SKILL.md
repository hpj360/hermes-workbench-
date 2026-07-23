---
name: frontend-design
description: Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, or applications. Generates creative, polished code that avoids generic AI aesthetics.
license: Complete terms in LICENSE.txt
---

This skill guides creation of distinctive, production-grade frontend interfaces that avoid generic "AI slop" aesthetics. Implement real working code with exceptional attention to aesthetic details and creative choices.

The user provides frontend requirements: a component, page, application, or interface to build. They may include context about the purpose, audience, or technical constraints.

## Design Thinking

Before coding, understand the context and commit to a BOLD aesthetic direction:
- **Purpose**: What problem does this interface solve? Who uses it?
- **Tone**: Pick an extreme: brutally minimal, maximalist chaos, retro-futuristic, organic/natural, luxury/refined, playful/toy-like, editorial/magazine, brutalist/raw, art deco/geometric, soft/pastel, industrial/utilitarian, etc. There are so many flavors to choose from. Use these for inspiration but design one that is true to the aesthetic direction.
- **Constraints**: Technical requirements (framework, performance, accessibility).
- **Differentiation**: What makes this UNFORGETTABLE? What's the one thing someone will remember?

**CRITICAL**: Choose a clear conceptual direction and execute it with precision. Bold maximalism and refined minimalism both work - the key is intentionality, not intensity.

Then implement working code (HTML/CSS/JS, React, Vue, etc.) that is:
- Production-grade and functional
- Visually striking and memorable
- Cohesive with a clear aesthetic point-of-view
- Meticulously refined in every detail

## Frontend Aesthetics Guidelines

Focus on:
- **Typography**: Choose fonts that are beautiful, unique, and interesting. Avoid generic fonts like Arial and Inter; opt instead for distinctive choices that elevate the frontend's aesthetics; unexpected, characterful font choices. Pair a distinctive display font with a refined body font.
- **Color & Theme**: Commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with sharp accents outperform timid, evenly-distributed palettes.
- **Motion**: Use animations for effects and micro-interactions. Prioritize CSS-only solutions for HTML. Use Motion library for React when available. Focus on high-impact moments: one well-orchestrated page load with staggered reveals (animation-delay) creates more delight than scattered micro-interactions. Use scroll-triggering and hover states that surprise.
- **Spatial Composition**: Unexpected layouts. Asymmetry. Overlap. Diagonal flow. Grid-breaking elements. Generous negative space OR controlled density.
- **Backgrounds & Visual Details**: Create atmosphere and depth rather than defaulting to solid colors. Add contextual effects and textures that match the overall aesthetic. Apply creative forms like gradient meshes, noise textures, geometric patterns, layered transparencies, dramatic shadows, decorative borders, custom cursors, and grain overlays.

NEVER use generic AI-generated aesthetics like overused font families (Inter, Roboto, Arial, system fonts), cliched color schemes (particularly purple gradients on white backgrounds), predictable layouts and component patterns, and cookie-cutter design that lacks context-specific character.

Interpret creatively and make unexpected choices that feel genuinely designed for the context. No design should be the same. Vary between light and dark themes, different fonts, different aesthetics. NEVER converge on common choices (Space Grotesk, for example) across generations.

**IMPORTANT**: Match implementation complexity to the aesthetic vision. Maximalist designs need elaborate code with extensive animations and effects. Minimalist or refined designs need restraint, precision, and careful attention to spacing, typography, and subtle details. Elegance comes from executing the vision well.

Remember: Claude is capable of extraordinary creative work. Don't hold back, show what can truly be created when thinking outside the box and committing fully to a distinctive vision.

---

## 标准工作流

### Step 1: 理解需求

**CHECKPOINT**: 是否明确了用户需求？
- 确认：界面的目的、目标用户、技术约束
- 确认：用户是否有设计偏好或风格限制
- 如果不明确：询问用户"您想要什么风格的界面？有什么具体要求吗？"

### Step 2: 确定设计方向

在动手前，确定大胆的设计方向：
- **基调**：极简主义 / 极繁主义 / 复古未来 / 有机自然 / 奢华精致 / 活泼玩具风 / 编辑杂志风 / 粗野主义 / 新艺术几何 / 柔和粉彩 / 工业实用 等
- **差异化**：什么是用户会记住的一个亮点？
- **技术栈**：HTML+CSS / React / Vue / Next.js / 其他

**CHECKPOINT**: 是否选择了清晰的设计方向？
- 是：执行 Step 3
- 否：选择一个方向并向用户确认

### Step 3: 编写代码

遵循设计原则编写代码：
- 使用独特字体（非 Inter/Roboto/Arial）
- 使用有凝聚力的配色方案
- 添加有意义的动画效果
- 打破常规布局（不对称、重叠、斜向流动）
- 创建氛围和深度而非纯色背景

**CHECKPOINT**: 代码是否可运行？
- 是：展示给用户
- 否：修复错误或简化设计

### Step 4: 交付并确认

向用户展示完整的代码，说明设计亮点，询问是否有调整需求。

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| 生成的代码有语法错误 | 设计复杂度超出实现能力 | 简化设计，优先保证代码可运行 |
| 设计过于相似 | 选择了保守的方向 | 重新选择更大胆的设计方向 |
| 用户不喜欢风格 | 设计方向不符合用户预期 | 询问用户偏好，重新生成 |
| 页面加载慢 | CSS/JS 过于复杂 | 优化代码，移除不必要的动画 |
| 响应式布局问题 | 未考虑移动端 | 添加响应式媒体查询 |

### 失败时的用户通知

```
⚠️ 生成的界面未能完全满足要求

原因：
- 设计方向可能需要调整
- 或者技术实现有难度

建议：
1. 请告诉我您不喜欢哪些方面
2. 您有参考的设计风格吗？
3. 我们可以基于您的反馈重新生成
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 使用 Inter/Roboto/Arial 系统字体 | 通用 AI 感 | 选择独特字体（Google Fonts 找稀有字体） |
| ❌ 使用紫色渐变白色背景 | 俗套配色 | 有凝聚力的配色方案（深色+亮色点缀） |
| ❌ 生成相同的界面 | 无差异化 | 每个界面都有独特设计方向 |
| ❌ 生成无法运行的代码 | 质量低 | 先保证可运行，再优化视觉效果 |
| ❌ 不考虑响应式 | 移动端体验差 | 每个界面都包含响应式设计 |

### 错误示例（反例）

**❌ 错误示例：保守设计**

```html
<!-- 使用通用字体、紫色渐变、标准卡片布局 -->
<div class="card">
  <h2 style="font-family: Inter;">标题</h2>
  <p style="background: linear-gradient(purple, white);">内容</p>
</div>
```

**✅ 正确做法**：

```html
<!-- 选择独特字体、有凝聚力的深色配色 -->
<div class="card">
  <h2 style="font-family: 'Playfair Display';">标题</h2>
  <p style="background: #1a1a2e; color: #eaeaea;">内容</p>
</div>
```

---

## FAQ 常见问题

**Q: 什么样的设计才算"有辨识度"？**
A: 用户看到后能记住这个界面，而不是"看起来和其他界面一样"。关键：独特字体 + 有特色的配色 + 非对称布局 + 有意义的动效。

**Q: 如何选择合适的字体？**
A: Google Fonts 上找非热门字体。Display 字体用于标题（如 Playfair Display、Cinzel），Body 字体用于正文（如 Crimson Text、Source Serif）。

**Q: 动画会不会影响性能？**
A: 优先使用 CSS 动画而非 JavaScript 动画。只在关键时刻添加动画（如页面加载、悬停反馈），避免过度动画。

**Q: 如何平衡创意和可用性？**
A: 在保证功能可用的前提下追求创意。表单要能提交、按钮要能点击、导航要能跳转——这些都是底线。

**Q: 如何处理深色/浅色主题？**
A: 使用 CSS 变量定义颜色，切换主题只需修改变量值。每个界面可以提供一个主题切换功能。
