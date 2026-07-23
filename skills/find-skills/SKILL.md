---
name: find-skills
description: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.
---

# Find Skills

This skill helps you discover and install skills from the open agent skills ecosystem.

## When to Use This Skill

Use this skill when the user:

- Asks "how do I do X" where X might be a common task with an existing skill
- Says "find a skill for X" or "is there a skill for X"
- Asks "can you do X" where X is a specialized capability
- Expresses interest in extending agent capabilities
- Wants to search for tools, templates, or workflows
- Mentions they wish they had help with a specific domain (design, testing, deployment, etc.)

## What is the Skills CLI?

The Skills CLI (`npx skills`) is the package manager for the open agent skills ecosystem. Skills are modular packages that extend agent capabilities with specialized knowledge, workflows, and tools.

**Key commands:**

- `npx skills find [query]` - Search for skills interactively or by keyword
- `npx skills add <package>` - Install a skill from GitHub or other sources
- `npx skills check` - Check for skill updates
- `npx skills update` - Update all installed skills

**Browse skills at:** https://skills.sh/

## How to Help Users Find Skills

### Step 1: Understand What They Need

When a user asks for help with something, identify:

1. The domain (e.g., React, testing, design, deployment)
2. The specific task (e.g., writing tests, creating animations, reviewing PRs)
3. Whether this is a common enough task that a skill likely exists

### Step 2: Search for Skills

Run the find command with a relevant query:

```bash
npx skills find [query]
```

For example:

- User asks "how do I make my React app faster?" → `npx skills find react performance`
- User asks "can you help me with PR reviews?" → `npx skills find pr review`
- User asks "I need to create a changelog" → `npx skills find changelog`

The command will return results like:

```
Install with npx skills add <owner/repo@skill>

vercel-labs/agent-skills@vercel-react-best-practices
└ https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices
```

### Step 3: Present Options to the User

When you find relevant skills, present them to the user with:

1. The skill name and what it does
2. The install command they can run
3. A link to learn more at skills.sh

Example response:

```
I found a skill that might help! The "vercel-react-best-practices" skill provides
React and Next.js performance optimization guidelines from Vercel Engineering.

To install it:
npx skills add vercel-labs/agent-skills@vercel-react-best-practices

Learn more: https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices
```

### Step 4: Offer to Install

If the user wants to proceed, you can install the skill for them:

```bash
npx skills add <owner/repo@skill> -g -y
```

The `-g` flag installs globally (user-level) and `-y` skips confirmation prompts.

## Common Skill Categories

When searching, consider these common categories:

| Category        | Example Queries                          |
| --------------- | ---------------------------------------- |
| Web Development | react, nextjs, typescript, css, tailwind |
| Testing         | testing, jest, playwright, e2e           |
| DevOps          | deploy, docker, kubernetes, ci-cd        |
| Documentation   | docs, readme, changelog, api-docs        |
| Code Quality    | review, lint, refactor, best-practices   |
| Design          | ui, ux, design-system, accessibility     |
| Productivity    | workflow, automation, git                |

## Tips for Effective Searches

1. **Use specific keywords**: "react testing" is better than just "testing"
2. **Try alternative terms**: If "deploy" doesn't work, try "deployment" or "ci-cd"
3. **Check popular sources**: Many skills come from `vercel-labs/agent-skills` or `ComposioHQ/awesome-claude-skills`

---

## 标准工作流

### Step 1: 理解用户需求

识别用户想要的功能类型：
- **领域**（如 React、测试、设计、部署、文档）
- **具体任务**（如编写测试、创建动画、审查 PR）
- **是否有现成 skill**（这是一个通用到足以有 skill 的任务吗？）

**CHECKPOINT**: 是否明确了用户需求？
- 明确：进入搜索流程
- 不明确：询问用户"您想完成什么具体任务？"或给出建议方向

### Step 2: 检测 Skills CLI 可用性

**CHECKPOINT**: `npx skills` 命令是否可用？
- 验证：运行 `npx skills --help` 检查是否有此 CLI
- 可用：使用 skills CLI 搜索和安装
- 不可用：转向备用方案（搜索 GitHub 仓库、描述 skill 概念给用户）

### Step 3: 搜索相关 Skills

```bash
# 根据用户需求构造搜索关键词
npx skills find <domain> <task>

# 示例：
# 用户问 "如何加速 React 应用" → npx skills find react performance
# 用户问 "需要帮助做 PR review" → npx skills find pr review
# 用户问 "想创建 changelog" → npx skills find changelog
```

**CHECKPOINT**: 是否找到相关结果？
- 成功（有匹配 skill）：展示给用户
- 成功（无匹配）：告知用户并提供替代方案
- 命令失败：转向备用方案

### Step 4: 展示选项给用户

当找到相关 skills 时，向用户展示：
1. Skill 名称和功能简介
2. 安装命令（`npx skills add <owner/repo@skill>`）
3. 了解更多的链接（skills.sh）
4. 询问用户是否安装

**CHECKPOINT**: 用户是否确认安装？
- 是：执行安装
- 否：提供使用 skill 的帮助信息

### Step 5: 安装（如用户确认）

```bash
npx skills add <owner/repo@skill> -g -y
```

**CHECKPOINT**: 安装是否成功？
- 成功：展示新 skill 的关键信息（SKILL.md 摘要）
- 失败：展示错误信息，提供手动安装建议

---

## 降级策略（备用方案）

| 优先级 | 方案 | 适用场景 |
|--------|------|---------|
| Layer 1 | `npx skills find/add` | Skills CLI 正常可用时 |
| Layer 2 | 搜索 GitHub 仓库 | Skills CLI 不可用，但能搜索 |
| Layer 3 | 提供 skill.sh 链接 | 无法执行任何命令，仅提供信息 |

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| `npx skills` 命令不存在 | npm/npx 未安装或版本过低 | 提示用户安装 Node.js/npm；降级到 Layer 2 搜索 |
| 搜索无结果 | 关键词太特殊；skill 库中没有匹配 | 告知用户"目前没有现成的 skill"；提供替代方案（手动编写任务或创建自定义 skill） |
| 安装失败 | 网络问题、权限问题、仓库不存在 | 检查网络；尝试其他 skill 源；建议手动 `git clone` |
| GitHub 访问失败 | 企业网络限制、网络问题 | 提供 skill 名称让用户自己查找；描述 skill 功能让用户决定 |
| 找到多个相似 skill | 有多个候选 | 列出前 3 个，让用户选择；或推荐下载量/最新的 |
| skill 文档缺失 | 安装后无 SKILL.md 或描述不清 | 帮助用户阅读 skill 目录内容；如果质量差，建议卸载 |

### 失败时的用户通知

当 skill 搜索或安装失败时，**明确告知用户**：

```
❌ 搜索 "react-performance" skill 未找到结果

原因：
- skills 仓库中没有匹配的条目

建议：
1. 尝试不同关键词（如 "react optimization" 或 "performance"）
2. 我可以帮你直接完成任务（通用能力）
3. 你也可以创建自己的 skill: npx skills init my-skill

要我用方案 2（直接帮你完成任务）吗？
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 不经用户确认直接安装 | 用户可能不需要或不信任 | 展示选项，等待用户确认后安装 |
| ❌ 用用户 API token 执行未知 skill | 安全风险 | 仅安装来源可信的 skill；检查 skill 内容 |
| ❌ 忽略 skill 安装失败静默退出 | 用户不知道发生了什么 | 展示完整错误信息和解决方案 |
| ❌ 推荐低质量/未维护的 skill | 可能引入 bug 或安全问题 | 优先推荐有维护、有文档、来源官方的 skill |
| ❌ 每次都搜索相同关键词 | 低效 | 如果之前搜索过同样的词，直接展示上次结果或推荐已知 skill |
| ❌ 只通过一个渠道搜索 | 可能错过更好的替代 | 同时搜索多个来源（skills CLI、GitHub、skills.sh） |

### 错误示例（反例）

**❌ 错误示例 1：不经确认直接安装**

```
用户：有没有帮助代码审查的 skill？
执行：npx skills add some/random-code-review-skill
（无任何确认）
结果：用户可能不需要这个，或该 skill 质量有问题
```

**✅ 正确做法**：

```
1. npx skills find code review 搜索
2. 展示 2-3 个相关 skill 的名称、功能描述、来源
3. 让用户选择（或推荐最匹配的）
4. 等待用户确认后才执行 add
```

---

**❌ 错误示例 2：推荐未维护的 skill**

```
找到多个 skill，但推荐选择了一个2年前已废弃的
结果：用户安装后无法使用，需要卸载
```

**✅ 正确做法**：

```
在展示 skill 时，关注以下特征：
- skill 有完整的 SKILL.md 文档
- 仓库有活跃提交（最近 3 个月内有更新）
- skill 有清晰的使用示例
- 来源为官方或知名组织（如 vercel-labs）
优先推荐满足以上条件的 skill
```

---

**❌ 错误示例 3：找不到 skill 就放弃**

```
用户：有能帮我做数据库迁移的 skill 吗？
执行：npx skills find database migration
结果：无匹配
响应：抱歉没有找到
```

**✅ 正确做法**：

```
1. 承认没有现成的 skill
2. 提供用户选择：
   a. 我可以直接帮你完成任务（使用通用能力）
   b. 我可以帮你创建一个自定义 skill（npx skills init）
   c. 尝试其他相关关键词搜索
3. 让用户决定下一步
```

---

## FAQ 常见问题

**Q: find-skills 和 skill-manager 有什么区别？**
A: find-skills 帮助用户发现新 skill（搜索 + 安装建议）；skill-manager 管理已安装的 skill（列出、更新、卸载）。

**Q: npx skills 命令在哪里安装的？**
A: npm 会自动解析 `npx` 命令。如果系统没有 Node.js/npm，需要先安装 Node.js。

**Q: 安装的 skill 会持久存在吗？**
A: 使用 `-g` 全局安装后，skill 会在用户的配置目录中存在。在 OpenClaw 环境中，skill 目录自动从 `~/.openclaw/skills/` 加载。

**Q: 如果找到多个 skill，应该推荐哪个？**
A: 优先推荐：有完整文档（SKILL.md）、来源可信（官方/知名组织）、最近有更新、与用户需求最匹配的那一个。

**Q: 如何验证安装的 skill 是否有用？**
A: 阅读 skill 的 SKILL.md 内容，执行 skill 的示例命令，确认输出是否符合预期。

**Q: 用户说"这个 skill 没用"怎么办？**
A: 可以帮助卸载：`npx skills remove <package>`。同时收集反馈：什么功能缺失/不符合预期？是否需要寻找替代？

**Q: 能否同时安装多个 skill？**
A: 可以，但建议逐个安装：先确认一个 skill 的价值，再安装下一个。避免批量安装可能带来的管理负担。

**Q: skill 安装后如何更新？**
A: `npx skills check` 检查更新，`npx skills update` 更新所有 skill，或使用 skill-manager skill 的更新功能。

**Q: 有没有官方的 skill 目录页面？**
A: 有：https://skills.sh/ 可以浏览所有公开的 skill。

**Q: 如果用户想要的功能没有现成 skill，我应该怎么做？**
A: 1) 用通用能力直接帮用户完成任务；2) 建议用户创建自定义 skill（`npx skills init my-skill`）；3) 记录到改进建议中，供未来参考。
