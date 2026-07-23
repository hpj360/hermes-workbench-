---
name: self-improvement
description: "Captures learnings, errors, and corrections to enable continuous improvement. Use when: (1) A command or operation fails unexpectedly, (2) User corrects Claude ('No, that's wrong...', 'Actually...'), (3) User requests a capability that doesn't exist, (4) An external API or tool fails, (5) Claude realizes its knowledge is outdated or incorrect, (6) A better approach is discovered for a recurring task. Also review learnings before major tasks."
metadata:
---

# Self-Improvement Skill

Log learnings and errors to markdown files for continuous improvement. Coding agents can later process these into fixes, and important learnings get promoted to project memory.

## First-Use Initialisation

Before logging anything, ensure the `.learnings/` directory and files exist in the project or workspace root. If any are missing, create them:

```bash
mkdir -p .learnings
[ -f .learnings/LEARNINGS.md ] || printf "# Learnings\n\nCorrections, insights, and knowledge gaps captured during development.\n\n**Categories**: correction | insight | knowledge_gap | best_practice\n\n---\n" > .learnings/LEARNINGS.md
[ -f .learnings/ERRORS.md ] || printf "# Errors\n\nCommand failures and integration errors.\n\n---\n" > .learnings/ERRORS.md
[ -f .learnings/FEATURE_REQUESTS.md ] || printf "# Feature Requests\n\nCapabilities requested by the user.\n\n---\n" > .learnings/FEATURE_REQUESTS.md
```

Never overwrite existing files. This is a no-op if `.learnings/` is already initialised.

Do not log secrets, tokens, private keys, environment variables, or full source/config files unless the user explicitly asks for that level of detail. Prefer short summaries or redacted excerpts over raw command output or full transcripts.

If you want automatic reminders or setup assistance, use the opt-in hook workflow described in [Hook Integration](#hook-integration).

## Quick Reference

| Situation | Action |
|-----------|--------|
| Command/operation fails | Log to `.learnings/ERRORS.md` |
| User corrects you | Log to `.learnings/LEARNINGS.md` with category `correction` |
| User wants missing feature | Log to `.learnings/FEATURE_REQUESTS.md` |
| API/external tool fails | Log to `.learnings/ERRORS.md` with integration details |
| Knowledge was outdated | Log to `.learnings/LEARNINGS.md` with category `knowledge_gap` |
| Found better approach | Log to `.learnings/LEARNINGS.md` with category `best_practice` |
| Simplify/Harden recurring patterns | Log/update `.learnings/LEARNINGS.md` with `Source: simplify-and-harden` and a stable `Pattern-Key` |
| Similar to existing entry | Link with `**See Also**`, consider priority bump |
| Broadly applicable learning | Promote to `CLAUDE.md`, `AGENTS.md`, and/or `.github/copilot-instructions.md` |
| Workflow improvements | Promote to `AGENTS.md` (OpenClaw workspace) |
| Tool gotchas | Promote to `TOOLS.md` (OpenClaw workspace) |
| Behavioral patterns | Promote to `SOUL.md` (OpenClaw workspace) |

## OpenClaw Setup (Recommended)

OpenClaw is the primary platform for this skill. It uses workspace-based prompt injection with automatic skill loading.

### Installation

**Via ClawdHub (recommended):**
```bash
clawdhub install self-improving-agent
```

**Manual:**
```bash
git clone https://github.com/peterskoett/self-improving-agent.git ~/.openclaw/skills/self-improving-agent
```

Remade for openclaw from original repo : https://github.com/pskoett/pskoett-ai-skills - https://github.com/pskoett/pskoett-ai-skills/tree/main/skills/self-improvement

### Workspace Structure

OpenClaw injects these files into every session:

```
~/.openclaw/workspace/
├── AGENTS.md          # Multi-agent workflows, delegation patterns
├── SOUL.md            # Behavioral guidelines, personality, principles
├── TOOLS.md           # Tool capabilities, integration gotchas
├── MEMORY.md          # Long-term memory (main session only)
├── memory/            # Daily memory files
│   └── YYYY-MM-DD.md
└── .learnings/        # This skill's log files
    ├── LEARNINGS.md
    ├── ERRORS.md
    └── FEATURE_REQUESTS.md
```

### Create Learning Files

```bash
mkdir -p ~/.openclaw/workspace/.learnings
```

Then create the log files (or copy from `assets/`):
- `LEARNINGS.md` — corrections, knowledge gaps, best practices
- `ERRORS.md` — command failures, exceptions
- `FEATURE_REQUESTS.md` — user-requested capabilities

### Promotion Targets

When learnings prove broadly applicable, promote them to workspace files:

| Learning Type | Promote To | Example |
|---------------|------------|---------|
| Behavioral patterns | `SOUL.md` | "Be concise, avoid disclaimers" |
| Workflow improvements | `AGENTS.md` | "Spawn sub-agents for long tasks" |
| Tool gotchas | `TOOLS.md` | "Git push needs auth configured first" |

### Inter-Session Communication

OpenClaw provides tools to share learnings across sessions:

- **sessions_list** — View active/recent sessions
- **sessions_history** — Read another session's transcript  
- **sessions_send** — Send a learning to another session
- **sessions_spawn** — Spawn a sub-agent for background work

Use these only in trusted environments and only when the user explicitly wants cross-session sharing. Prefer sending a short sanitized summary and relevant file paths, not raw transcripts, secrets, or full command output.

### Optional: Enable Hook

For automatic reminders at session start:

```bash
# Copy hook to OpenClaw hooks directory
cp -r hooks/openclaw ~/.openclaw/hooks/self-improvement

# Enable it
openclaw hooks enable self-improvement
```

See `references/openclaw-integration.md` for complete details.

---

## Generic Setup (Other Agents)

For Claude Code, Codex, Copilot, or other agents, create `.learnings/` in the project or workspace root:

```bash
mkdir -p .learnings
```

Create the files inline using the headers shown above. Avoid reading templates from the current repo or workspace unless you explicitly trust that path.

### Add reference to agent files AGENTS.md, CLAUDE.md, or .github/copilot-instructions.md to remind yourself to log learnings. (this is an alternative to hook-based reminders)

#### Self-Improvement Workflow

When errors or corrections occur:
1. Log to `.learnings/ERRORS.md`, `LEARNINGS.md`, or `FEATURE_REQUESTS.md`
2. Review and promote broadly applicable learnings to:
   - `CLAUDE.md` - project facts and conventions
   - `AGENTS.md` - workflows and automation
   - `.github/copilot-instructions.md` - Copilot context

## Logging Format

### Learning Entry

Append to `.learnings/LEARNINGS.md`:

```markdown
## [LRN-YYYYMMDD-XXX] category

**Logged**: ISO-8601 timestamp
**Priority**: low | medium | high | critical
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config

### Summary
One-line description of what was learned

### Details
Full context: what happened, what was wrong, what's correct

### Suggested Action
Specific fix or improvement to make

### Metadata
- Source: conversation | error | user_feedback
- Related Files: path/to/file.ext
- Tags: tag1, tag2
- See Also: LRN-20250110-001 (if related to existing entry)
- Pattern-Key: simplify.dead_code | harden.input_validation (optional, for recurring-pattern tracking)
- Recurrence-Count: 1 (optional)
- First-Seen: 2025-01-15 (optional)
- Last-Seen: 2025-01-15 (optional)

---
```

### Error Entry

Append to `.learnings/ERRORS.md`:

```markdown
## [ERR-YYYYMMDD-XXX] skill_or_command_name

**Logged**: ISO-8601 timestamp
**Priority**: high
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config

### Summary
Brief description of what failed

### Error
```
Actual error message or output
```

### Context
- Command/operation attempted
- Input or parameters used
- Environment details if relevant
- Summary or redacted excerpt of relevant output (avoid full transcripts and secret-bearing data by default)

### Suggested Fix
If identifiable, what might resolve this

### Metadata
- Reproducible: yes | no | unknown
- Related Files: path/to/file.ext
- See Also: ERR-20250110-001 (if recurring)

---
```

### Feature Request Entry

Append to `.learnings/FEATURE_REQUESTS.md`:

```markdown
## [FEAT-YYYYMMDD-XXX] capability_name

**Logged**: ISO-8601 timestamp
**Priority**: medium
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config

### Requested Capability
What the user wanted to do

### User Context
Why they needed it, what problem they're solving

### Complexity Estimate
simple | medium | complex

### Suggested Implementation
How this could be built, what it might extend

### Metadata
- Frequency: first_time | recurring
- Related Features: existing_feature_name

---
```

## ID Generation

Format: `TYPE-YYYYMMDD-XXX`
- TYPE: `LRN` (learning), `ERR` (error), `FEAT` (feature)
- YYYYMMDD: Current date
- XXX: Sequential number or random 3 chars (e.g., `001`, `A7B`)

Examples: `LRN-20250115-001`, `ERR-20250115-A3F`, `FEAT-20250115-002`

## Resolving Entries

When an issue is fixed, update the entry:

1. Change `**Status**: pending` → `**Status**: resolved`
2. Add resolution block after Metadata:

```markdown
### Resolution
- **Resolved**: 2025-01-16T09:00:00Z
- **Commit/PR**: abc123 or #42
- **Notes**: Brief description of what was done
```

Other status values:
- `in_progress` - Actively being worked on
- `wont_fix` - Decided not to address (add reason in Resolution notes)
- `promoted` - Elevated to CLAUDE.md, AGENTS.md, or .github/copilot-instructions.md

## Promoting to Project Memory

When a learning is broadly applicable (not a one-off fix), promote it to permanent project memory.

### When to Promote

- Learning applies across multiple files/features
- Knowledge any contributor (human or AI) should know
- Prevents recurring mistakes
- Documents project-specific conventions

### Promotion Targets

| Target | What Belongs There |
|--------|-------------------|
| `CLAUDE.md` | Project facts, conventions, gotchas for all Claude interactions |
| `AGENTS.md` | Agent-specific workflows, tool usage patterns, automation rules |
| `.github/copilot-instructions.md` | Project context and conventions for GitHub Copilot |
| `SOUL.md` | Behavioral guidelines, communication style, principles (OpenClaw workspace) |
| `TOOLS.md` | Tool capabilities, usage patterns, integration gotchas (OpenClaw workspace) |

### How to Promote

1. **Distill** the learning into a concise rule or fact
2. **Add** to appropriate section in target file (create file if needed)
3. **Update** original entry:
   - Change `**Status**: pending` → `**Status**: promoted`
   - Add `**Promoted**: CLAUDE.md`, `AGENTS.md`, or `.github/copilot-instructions.md`

### Promotion Examples

**Learning** (verbose):
> Project uses pnpm workspaces. Attempted `npm install` but failed. 
> Lock file is `pnpm-lock.yaml`. Must use `pnpm install`.

**In CLAUDE.md** (concise):
```markdown
## Build & Dependencies
- Package manager: pnpm (not npm) - use `pnpm install`
```

**Learning** (verbose):
> When modifying API endpoints, must regenerate TypeScript client.
> Forgetting this causes type mismatches at runtime.

**In AGENTS.md** (actionable):
```markdown
## After API Changes
1. Regenerate client: `pnpm run generate:api`
2. Check for type errors: `pnpm tsc --noEmit`
```

## Recurring Pattern Detection

If logging something similar to an existing entry:

1. **Search first**: `grep -r "keyword" .learnings/`
2. **Link entries**: Add `**See Also**: ERR-20250110-001` in Metadata
3. **Bump priority** if issue keeps recurring
4. **Consider systemic fix**: Recurring issues often indicate:
   - Missing documentation (→ promote to CLAUDE.md or .github/copilot-instructions.md)
   - Missing automation (→ add to AGENTS.md)
   - Architectural problem (→ create tech debt ticket)

## Simplify & Harden Feed

Use this workflow to ingest recurring patterns from the `simplify-and-harden`
skill and turn them into durable prompt guidance.

### Ingestion Workflow

1. Read `simplify_and_harden.learning_loop.candidates` from the task summary.
2. For each candidate, use `pattern_key` as the stable dedupe key.
3. Search `.learnings/LEARNINGS.md` for an existing entry with that key:
   - `grep -n "Pattern-Key: <pattern_key>" .learnings/LEARNINGS.md`
4. If found:
   - Increment `Recurrence-Count`
   - Update `Last-Seen`
   - Add `See Also` links to related entries/tasks
5. If not found:
   - Create a new `LRN-...` entry
   - Set `Source: simplify-and-harden`
   - Set `Pattern-Key`, `Recurrence-Count: 1`, and `First-Seen`/`Last-Seen`

### Promotion Rule (System Prompt Feedback)

Promote recurring patterns into agent context/system prompt files when all are true:

- `Recurrence-Count >= 3`
- Seen across at least 2 distinct tasks
- Occurred within a 30-day window

Promotion targets:
- `CLAUDE.md`
- `AGENTS.md`
- `.github/copilot-instructions.md`
- `SOUL.md` / `TOOLS.md` for OpenClaw workspace-level guidance when applicable

Write promoted rules as short prevention rules (what to do before/while coding),
not long incident write-ups.

## Periodic Review

Review `.learnings/` at natural breakpoints:

### When to Review
- Before starting a new major task
- After completing a feature
- When working in an area with past learnings
- Weekly during active development

### Quick Status Check
```bash
# Count pending items
grep -h "Status\*\*: pending" .learnings/*.md | wc -l

# List pending high-priority items
grep -B5 "Priority\*\*: high" .learnings/*.md | grep "^## \["

# Find learnings for a specific area
grep -l "Area\*\*: backend" .learnings/*.md
```

### Review Actions
- Resolve fixed items
- Promote applicable learnings
- Link related entries
- Escalate recurring issues

## Detection Triggers

Automatically log when you notice:

**Corrections** (→ learning with `correction` category):
- "No, that's not right..."
- "Actually, it should be..."
- "You're wrong about..."
- "That's outdated..."

**Feature Requests** (→ feature request):
- "Can you also..."
- "I wish you could..."
- "Is there a way to..."
- "Why can't you..."

**Knowledge Gaps** (→ learning with `knowledge_gap` category):
- User provides information you didn't know
- Documentation you referenced is outdated
- API behavior differs from your understanding

**Errors** (→ error entry):
- Command returns non-zero exit code
- Exception or stack trace
- Unexpected output or behavior
- Timeout or connection failure

## Priority Guidelines

| Priority | When to Use |
|----------|-------------|
| `critical` | Blocks core functionality, data loss risk, security issue |
| `high` | Significant impact, affects common workflows, recurring issue |
| `medium` | Moderate impact, workaround exists |
| `low` | Minor inconvenience, edge case, nice-to-have |

## Area Tags

Use to filter learnings by codebase region:

| Area | Scope |
|------|-------|
| `frontend` | UI, components, client-side code |
| `backend` | API, services, server-side code |
| `infra` | CI/CD, deployment, Docker, cloud |
| `tests` | Test files, testing utilities, coverage |
| `docs` | Documentation, comments, READMEs |
| `config` | Configuration files, environment, settings |

## Best Practices

1. **Log immediately** - context is freshest right after the issue
2. **Be specific** - future agents need to understand quickly
3. **Include reproduction steps** - especially for errors
4. **Link related files** - makes fixes easier
5. **Suggest concrete fixes** - not just "investigate"
6. **Use consistent categories** - enables filtering
7. **Promote aggressively** - if in doubt, add to CLAUDE.md or .github/copilot-instructions.md
8. **Review regularly** - stale learnings lose value

## Gitignore Options

**Keep learnings local** (per-developer):
```gitignore
.learnings/
```

This repo uses that default to avoid committing sensitive or noisy local logs by accident.

**Track learnings in repo** (team-wide):
Don't add to .gitignore - learnings become shared knowledge.

**Hybrid** (track templates, ignore entries):
```gitignore
.learnings/*.md
!.learnings/.gitkeep
```

## Hook Integration

Enable automatic reminders through agent hooks. This is **opt-in** - you must explicitly configure hooks.

### Quick Setup (Claude Code / Codex)

Create `.claude/settings.json` in your project:

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "./skills/self-improvement/scripts/activator.sh"
      }]
    }]
  }
}
```

This injects a learning evaluation reminder after each prompt (~50-100 tokens overhead).

### Advanced Setup (With Error Detection)

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "./skills/self-improvement/scripts/activator.sh"
      }]
    }],
    "PostToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "./skills/self-improvement/scripts/error-detector.sh"
      }]
    }]
  }
}
```

This is optional. The recommended default is activator-only setup; enable `PostToolUse` only if you are comfortable with hook scripts inspecting command output for error patterns.

### Available Hook Scripts

| Script | Hook Type | Purpose |
|--------|-----------|---------|
| `scripts/activator.sh` | UserPromptSubmit | Reminds to evaluate learnings after tasks |
| `scripts/error-detector.sh` | PostToolUse (Bash) | Triggers on command errors |

See `references/hooks-setup.md` for detailed configuration and troubleshooting.

## Automatic Skill Extraction

When a learning is valuable enough to become a reusable skill, extract it using the provided helper.

### Skill Extraction Criteria

A learning qualifies for skill extraction when ANY of these apply:

| Criterion | Description |
|-----------|-------------|
| **Recurring** | Has `See Also` links to 2+ similar issues |
| **Verified** | Status is `resolved` with working fix |
| **Non-obvious** | Required actual debugging/investigation to discover |
| **Broadly applicable** | Not project-specific; useful across codebases |
| **User-flagged** | User says "save this as a skill" or similar |

### Extraction Workflow

1. **Identify candidate**: Learning meets extraction criteria
2. **Run helper** (or create manually):
   ```bash
   ./skills/self-improvement/scripts/extract-skill.sh skill-name --dry-run
   ./skills/self-improvement/scripts/extract-skill.sh skill-name
   ```
3. **Customize SKILL.md**: Fill in template with learning content
4. **Update learning**: Set status to `promoted_to_skill`, add `Skill-Path`
5. **Verify**: Read skill in fresh session to ensure it's self-contained

### Manual Extraction

If you prefer manual creation:

1. Create `skills/<skill-name>/SKILL.md`
2. Use template from `assets/SKILL-TEMPLATE.md`
3. Follow [Agent Skills spec](https://agentskills.io/specification):
   - YAML frontmatter with `name` and `description`
   - Name must match folder name
   - No README.md inside skill folder

### Extraction Detection Triggers

Watch for these signals that a learning should become a skill:

**In conversation:**
- "Save this as a skill"
- "I keep running into this"
- "This would be useful for other projects"
- "Remember this pattern"

**In learning entries:**
- Multiple `See Also` links (recurring issue)
- High priority + resolved status
- Category: `best_practice` with broad applicability
- User feedback praising the solution

### Skill Quality Gates

Before extraction, verify:

- [ ] Solution is tested and working
- [ ] Description is clear without original context
- [ ] Code examples are self-contained
- [ ] No project-specific hardcoded values
- [ ] Follows skill naming conventions (lowercase, hyphens)

## Multi-Agent Support

This skill works across different AI coding agents with agent-specific activation.

### Claude Code

**Activation**: Hooks (UserPromptSubmit, PostToolUse)
**Setup**: `.claude/settings.json` with hook configuration
**Detection**: Automatic via hook scripts

### Codex CLI

**Activation**: Hooks (same pattern as Claude Code)
**Setup**: `.codex/settings.json` with hook configuration
**Detection**: Automatic via hook scripts

### GitHub Copilot

**Activation**: Manual (no hook support)
**Setup**: Add to `.github/copilot-instructions.md`:

```markdown
## Self-Improvement

After solving non-obvious issues, consider logging to `.learnings/`:
1. Use format from self-improvement skill
2. Link related entries with See Also
3. Promote high-value learnings to skills

Ask in chat: "Should I log this as a learning?"
```

**Detection**: Manual review at session end

---

## 标准工作流

### Step 1: 触发检测

self-improvement 有两种触发模式：**事件触发**（被动）和 **周期触发**（主动，GEPA 模式）。

#### 模式 A：事件触发（被动）

当以下任一情况发生时，触发 self-improvement 流程：
- 命令或操作意外失败
- 用户纠正了 Claude 的回答
- 用户请求不存在的能力
- 外部 API/工具失败
- 知识过时或不正确
- 发现更好的做事方法

**CHECKPOINT**: 这是否需要记录？
- 记录：如果问题涉及可重复的模式或可能再次发生的错误
- 跳过：如果这是简单的拼写错误或一次性问题不会重复

#### 模式 B：周期触发（GEPA 模式，借鉴 Hermes Agent）

每 **N 次工具调用**（默认 N=15）后，自动触发一次会话评估。

**GEPA 评估流程**：

```
工具调用计数器 → 达到阈值(15次) → 暂停评估
                                    ↓
                    ┌───────────────────────────────┐
                    │  1. 模式识别                    │
                    │     - 本次会话出现了什么模式？    │
                    │     - 哪些步骤被重复执行？       │
                    │     - 哪些工具被频繁调用？       │
                    │                               │
                    │  2. 步骤提取                    │
                    │     - 成功的步骤序列是什么？     │
                    │     - 失败的步骤有哪些？        │
                    │     - 有没有更优的路径？        │
                    │                               │
                    │  3. 可复用性判断                 │
                    │     - 这个模式是否通用？         │
                    │     - 是否跨项目可用？          │
                    │     - 是否非显而易见？          │
                    │     - 是否已被验证有效？        │
                    │                               │
                    │  4. 决策                        │
                    │     是 → 写入 skill 文件        │
                    │     否 → 继续执行               │
                    └───────────────────────────────┘
```

**GEPA 评估检查清单**：

- [ ] 本次会话是否有重复的操作模式？（同一类操作执行了 2 次以上）
- [ ] 是否发现了非显而易见的解决方案？（需要调试或探索才发现）
- [ ] 这个模式是否可以在其他项目中复用？
- [ ] 是否有步骤可以被自动化或封装为工具？
- [ ] 是否有错误模式值得记录以避免重复？

**GEPA 技能提取标准**（满足任意 2 条即可提取）：

| 标准 | 说明 |
|------|------|
| 重复性 | 同一模式在本会话中出现 2+ 次 |
| 非显而易见 | 需要实际调试/探索才发现，不是常识 |
| 可验证 | 步骤已被验证有效 |
| 通用性 | 不是项目特定，可跨项目复用 |

**GEPA 记录格式**：

```markdown
## [GEPA-YYYYMMDD-XXX] pattern_name

**Logged**: ISO-8601 timestamp
**Trigger**: periodic_eval (tool_calls: 15)
**Source**: GEPA auto-evaluation
**Area**: frontend | backend | infra | tests | docs | config

### Pattern
描述发现的模式

### Steps
1. 步骤一
2. 步骤二
3. 步骤三

### Reusability
- 通用性：高/中/低
- 适用场景：...

### Skill Extraction
- 是否提取为 skill：是/否
- 如果是，skill 路径：skills/<skill-name>/SKILL.md
```

### Step 2: 记录日志

根据类型选择日志文件：

```bash
# 学习内容 → .learnings/LEARNINGS.md
# 错误 → .learnings/ERRORS.md
# 功能请求 → .learnings/FEATURE_REQUESTS.md
```

**CHECKPOINT**: 是否存在 `.learnings/` 目录？
- 不存在 → 先执行初始化（First-Use Initialisation）
- 存在 → 继续记录

**CHECKPOINT**: 是否已经有相似的条目？
- 搜索文件查找相似内容
- 如果存在，更新现有条目（增加优先级）而非重复记录
- 如果不存在，添加新条目

### Step 3: 评估升级

**CHECKPOINT**: 是否应该升级（Promotion）？
- 升级条件：
  - 已在多个项目/场景中被证明有用
  - 是通用模式，不是特定项目的技巧
  - 已被用户确认是重要的最佳实践
- 升级目的地：
  - **操作流程** → AGENTS.md
  - **工具技巧** → TOOLS.md
  - **行为模式** → SOUL.md
  - **核心指导** → CLAUDE.md

### Step 4: Skill 提取（可选）

如果一个模式被多次证明有效，可以考虑提取为独立的 skill。

**Skill 质量门禁**（提取前验证）：
- [ ] 解决方案已测试并正常工作
- [ ] 描述在没有原始上下文的情况下也能理解
- [ ] 代码示例是自包含的
- [ ] 没有项目特定的硬编码值
- [ ] 遵循 skill 命名规范（小写，连字符）

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| `.learnings/` 目录不存在 | 首次使用，未初始化 | 执行 First-Use Initialisation 创建目录和文件 |
| 文件写入权限错误 | 文件系统权限问题 | 提示用户检查路径权限，或使用 `sudo` |
| 日志格式不一致 | 不同条目格式不同 | 参考 Quick Reference 表格统一格式 |
| 重复记录 | 同一问题被多次记录 | 搜索现有条目，更新而非添加新条目 |
| 升级判断错误 | 过度记录或记录不足 | 基于 Promotion Checklist 进行决策 |

### 失败时的用户通知

当 self-improvement 操作失败时，**明确告知用户**：

**示例**：
```
⚠️  无法写入 .learnings/LEARNINGS.md

原因：文件系统权限不足

建议：
- 检查当前目录是否有写入权限
- 或手动创建目录：mkdir -p .learnings
- 或修改文件权限：chmod 644 .learnings/*.md

我可以为您执行这些命令吗？
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 记录 secrets/tokens/私钥 | 严重安全风险 | 总结时删除/脱敏敏感信息 |
| ❌ 记录完整源代码/配置文件 | 数据泄露风险 | 使用简短摘要或脱敏摘录 |
| ❌ 过度记录每个操作 | 产生噪音，适得其反 | 只记录可能会重复的错误和改进 |
| ❌ 不检查重复直接追加 | 导致日志膨胀 | 先搜索再追加，相似内容更新现有条目 |
| ❌ 直接跳过记录 | 失去改进机会 | 至少记录关键词和错误类型 |
| ❌ 每次都询问用户 | 降低生产力 | 自动判断，只有不确定时才询问 |

### 错误示例（反例）

**❌ 错误示例 1：记录敏感信息**

```
## 错误记录

错误：数据库连接失败
查询：SELECT * FROM users WHERE token = "sk-123456789"
```

**问题**：暴露了 API Key/token

**✅ 正确做法**：

```
## 错误记录

错误：数据库连接失败（认证错误）
修复：验证环境变量中的数据库凭证是否正确
模式：确保在连接数据库前检查凭证的存在性
```

---

**❌ 错误示例 2：不检查重复**

```bash
# 每次都直接追加
echo "## 新学习\n..." >> .learnings/LEARNINGS.md
```

**问题**：相同问题被重复记录，日志膨胀

**✅ 正确做法**：

```bash
# 先搜索是否有相似条目
grep -i "关键词" .learnings/LEARNINGS.md
# 如果存在，更新现有条目
# 如果不存在，追加新条目
```

---

**❌ 错误示例 3：过度升级**

将简单的命令行技巧直接升级为 skill

**问题**：创建了大量微小的 skill，管理成本高

**✅ 正确做法**：

- 先记录在 LEARNINGS.md
- 观察是否在多个项目中重复出现
- 确认 3 次以上后，才考虑升级为 skill

---

## FAQ 常见问题

**Q: 什么时候应该记录，什么时候跳过？**
A: 如果这个问题/模式可能在未来再次发生，就记录。简单的拼写错误或一次性问题可以跳过。

**Q: 日志文件会不会变得太大？**
A: 定期（例如每周）审查日志，将重复内容合并，将过时内容删除。将高价值的学习内容升级为 skill。

**Q: 应该如何分类（correction/insight/knowledge_gap/best_practice）？**
A: correction = 用户纠正了你的错误；insight = 你发现了新的理解；knowledge_gap = 你意识到知识不足；best_practice = 你发现了更好的做事方法。

**Q: 升级到 skill 后，原日志要删除吗？**
A: 不要删除，保留作为历史记录。可以添加 "→ 已升级为 skill: skill-name" 的链接。

**Q: 多个 Agent 如何共享学习内容？**
A: `.learnings/` 目录应该放在项目根目录，所有 Agent 都能访问。团队共享的内容可以考虑放入知识库。

**Q: 用户不想让我记录怎么办？**
A: 尊重用户意愿。可以只在内存中保留，不写入文件。询问用户"我应该记录这个学习内容吗？"

**Q: 日志文件格式有要求吗？**
A: 使用 Markdown，方便阅读和搜索。每条记录包含：标题、日期、描述、修复方式（如适用）、模式 Key。

**Q: 如何搜索历史日志？**
A: 使用 `grep -i "关键词" .learnings/*.md` 搜索。或者用 `cat .learnings/LEARNINGS.md` 浏览所有学习内容。
