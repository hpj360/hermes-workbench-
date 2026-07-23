---
name: storybook-chromatic
description: Figma → Storybook → Chromatic 视觉回归 → design-code 闭环工具。自动生成 CSF 3.0 故事、调用 Chromatic 视觉回归、解析 PR 检查结果。触发场景：用户说"建 Storybook""组件可视化""视觉回归""Chromatic 集成""design-code 同步""组件库文档化"。
license: Apache-2.0
---

# Storybook + Chromatic 集成

把 Figma 设计稿转化为 Storybook 组件故事，通过 Chromatic 视觉回归建立 design-code 闭环。

## 5 步闭环

```
1. Figma 组件 (figma-reader 提取)
        ↓
2. 生成 React 组件代码（占位）
        ↓
3. 生成 CSF 3.0 故事（自动枚举 props 变体）
        ↓
4. Chromatic 视觉回归（PR 检查）
        ↓
5. 设计/开发评审（PR 评论含截图 diff）
```

## 依赖

```bash
# Node.js
npm install -D @storybook/react @storybook/react-vite storybook chromatic

# Python 工具（本 skill）
pip install requests
```

## 基础用法

```bash
# 1. 初始化项目 Storybook 配置
python3 scripts/init_storybook.py /path/to/project --output .storybook/

# 2. 从 Figma 组件生成 React 组件 + Story
python3 scripts/sync_figma_to_story.py \
  --figma-key ABC123 \
  --component-key btn-primary \
  --output src/components/Button/

# 3. 批量生成所有组件故事
python3 scripts/sync_figma_to_story.py --figma-key ABC123 --all --output src/

# 4. 运行 Chromatic（需要 CHROMATIC_PROJECT_TOKEN）
python3 scripts/run_chromatic.py --token $CHROMATIC_PROJECT_TOKEN

# 5. 解析 PR 检查结果
python3 scripts/review_pr.py --pr-number 123 --output review.json
```

## 4 大功能

### 1. CSF 3.0 故事生成
自动从 Figma 组件 props 描述生成 Storybook CSF 3.0：
```typescript
export default { component: Button, title: 'Components/Button' } as Meta;
export const Primary: StoryObj<typeof Button> = {
  args: { variant: 'primary', size: 'md', children: 'Click me' }
};
```

### 2. Chromatic 集成
- 调用 `npx chromatic` 跑视觉回归
- 解析输出（含 baseline 对比、PR 检查链接）
- 自动上传到 Chromatic 云

### 3. PR 评论
- 解析 Chromatic 视觉回归报告
- 提取变更截图、差异百分比
- 在 PR 评论里嵌入对比截图

### 4. 双向同步
- Figma 改了 → 同步代码（提示差异）
- 代码改了 → 同步 Figma（标记 review）

## Story 模板（CSF 3.0）

```typescript
import type { Meta, StoryObj } from '@storybook/react';
import { Button } from './Button';

const meta: Meta<typeof Button> = {
  title: 'Components/Button',
  component: Button,
  parameters: { layout: 'centered' },
  tags: ['autodocs'],
  argTypes: {
    variant: { control: 'select', options: ['primary', 'secondary', 'ghost'] },
    size:    { control: 'select', options: ['sm', 'md', 'lg'] },
    disabled: { control: 'boolean' },
  },
};
export default meta;
type Story = StoryObj<typeof Button>;

export const Primary: Story = {
  args: { variant: 'primary', size: 'md', children: 'Primary Button' },
};

export const Disabled: Story = {
  args: { variant: 'primary', size: 'md', children: 'Disabled', disabled: true },
};
```

## Chromatic 工作流

```yaml
# .github/workflows/chromatic.yml
name: Chromatic
on: [push, pull_request]
jobs:
  chromatic:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - uses: chromaui/action@v1
        with:
          projectToken: ${{ secrets.CHROMATIC_PROJECT_TOKEN }}
```

## 与其他 skill 配合

| Skill | 关系 |
|---|---|
| `figma-reader` | 提供 Figma 组件元数据 |
| `component-library-selector` | 选完库后用此 skill 包装 |
| `style-dictionary-sync` | token 同步到主题 |
| `prototype-validator` | 运行时验证 |
| `ui-review-checklist` | 静态代码审查 |

## 不适用

- 纯静态 HTML（非 React 组件）
- 高度动态的组件（动画/数据可视化）
- Figma 库版本管理（用 Figma 自身）
