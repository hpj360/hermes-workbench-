---
name: github
description: "Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries. 也适用于用户提到 GitHub 仓库、PR 状态、CI/CD、Issue 管理等场景。"
---

# GitHub Skill

使用 `gh` CLI 与 GitHub 交互。始终指定 `--repo owner/repo`（不在 git 目录时）或直接使用 URL。

## 标准工作流

### Step 1: 检测 gh CLI 可用性

**CHECKPOINT**: `gh` 命令是否可用？
- 验证：`which gh` 或 `gh --version`
- 可用：继续
- 不可用：提示用户安装（`brew install gh`）

**CHECKPOINT**: 是否已登录？
- 验证：`gh auth status`
- 已登录：继续
- 未登录：提示用户 `gh auth login`

### Step 2: 确定用户需求

| 需求类型 | 对应命令 |
|---------|---------|
| 检查 PR CI 状态 | `gh pr checks` |
| 查看 Issue 列表 | `gh issue list` |
| 查看 CI 运行记录 | `gh run list` |
| 查看 CI 日志 | `gh run view <id> --log` |
| 高级 API 查询 | `gh api` |
| 创建 Issue | `gh issue create` |
| 创建 PR | `gh pr create` |

### Step 3: 执行命令

#### PR 操作

```bash
# 检查 PR CI 状态
gh pr checks 55 --repo owner/repo

# 查看 PR 详情
gh pr view 55 --repo owner/repo

# 查看 PR 差异
gh pr diff 55 --repo owner/repo

# 创建 PR
gh pr create --title "Fix bug" --body "Description" --repo owner/repo
```

#### Issue 操作

```bash
# 列出 Issue（支持状态筛选）
gh issue list --repo owner/repo --state open --limit 10

# 查看 Issue 详情
gh issue view 123 --repo owner/repo

# 创建 Issue
gh issue create --title "Bug report" --body "Description" --repo owner/repo

# 关闭 Issue
gh issue close 123 --repo owner/repo
```

#### CI/CD 操作

```bash
# 列出最近运行记录
gh run list --repo owner/repo --limit 10

# 查看运行详情（包含步骤）
gh run view <run-id> --repo owner/repo

# 查看失败步骤日志
gh run view <run-id> --repo owner/repo --log-failed

# 触发工作流
gh workflow run <workflow-name> --repo owner/repo
```

#### API 高级查询

`gh api` 用于访问其他子命令无法获取的数据：

```bash
# 获取 PR 特定字段
gh api repos/owner/repo/pulls/55 --jq '.title, .state, .user.login'

# 获取 JSON 输出
gh issue list --repo owner/repo --json number,title,state,labels

# 过滤和格式化
gh issue list --repo owner/repo --json number,title --jq '.[] | "\(.number): \(.title)"'
```

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| gh 命令不存在 | gh 未安装 | 提示安装（brew/apt） |
| 未登录 | gh auth 未完成 | 提示 `gh auth login` |
| 认证过期 | token 失效 | 提示 `gh auth refresh` |
| 仓库不存在 | 拼写错误或无权限 | 检查 repo 名称和访问权限 |
| PR/Issue 不存在 | 编号错误 | 列出最近的内容确认编号 |
| API 限流 | 请求过快 | 等待后重试；使用 `--paginate` 分页 |
| 无网络连接 | 网络问题 | 检查网络连接 |

### 失败时的用户通知

```
❌ 无法访问仓库 owner/repo

原因：
- 仓库不存在或您没有访问权限
- 或者 gh 未登录

建议：
1. 检查仓库名称是否正确（owner/repo 格式）
2. 运行 gh auth status 检查登录状态
3. 如果是私有仓库，确保已获取访问权限
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 不检查登录状态直接操作 | 必然失败 | 先 `gh auth status` 确认 |
| ❌ 假设当前目录在 git 仓库中 | 可能操作错误仓库 | 始终指定 `--repo` 或确认当前目录 |
| ❌ 不处理 API 限流 | 请求被拒绝 | 添加延迟或使用 `--paginate` |
| ❌ 忽略权限错误 | 可能误操作其他仓库 | 确认 token 权限范围 |

### 错误示例（反例）

**❌ 错误示例 1：不检查登录状态**

```
执行：gh pr list
结果：报错 "not authenticated"
用户困惑：我以为已经登录了
```

**✅ 正确做法**：

```
执行前：
1. gh auth status
2. 如果未登录：gh auth login
3. 确认已登录后再执行操作
```

---

**❌ 错误示例 2：不指定仓库**

```
在 /home 目录执行 gh pr list
结果：报错 "could not determine repository"
```

**✅ 正确做法**：

```
gh pr list --repo owner/repo
# 或先 cd 到正确的 git 仓库目录再执行
```

---

## FAQ 常见问题

**Q: gh 和 git 命令有什么区别？**
A: gh 是 GitHub CLI（管理 GitHub 资源）；git 是版本控制工具（管理代码）。两者配合使用。

**Q: 如何查看所有可用命令？**
A: `gh help` 或 `gh <command> --help`。

**Q: 如何设置默认仓库？**
A: 在 git 仓库目录中执行 gh 会自动使用当前仓库，不需要 `--repo`。

**Q: API 限流了怎么办？**
A: GitHub API 未认证 60 次/小时，认证后 5000 次/小时。遇到限流等待后重试。

**Q: 如何查看其他人的仓库？**
A: 任何人都可以查看公开仓库，只需 `--repo owner/repo` 指定即可。私有仓库需要授权。

**Q: `--jq` 是什么？**
A: jq 是一种 JSON 处理语法。`--jq '.field'` 提取字段，`--json all` 返回完整 JSON。

**Q: 能用 gh 创建分支吗？**
A: 不能，创建分支用 git：`git checkout -b new-branch`。

**Q: 如何配置 gh 输出格式？**
A: `gh config set editor vim`，`gh config set pagination 20`。
