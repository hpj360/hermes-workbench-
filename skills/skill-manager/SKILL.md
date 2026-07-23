---
name: skill-manager
description: 管理所有已安装的skill，包括列出、安装、更新、卸载、搜索和配置管理
---

# Skill Manager

这个技能用于全面管理已安装的skill，提供完整的生命周期管理功能。

## 功能

- **列出技能**：显示所有已安装的skill及其状态
- **安装技能**：从skillhub或其他源安装新的skill
- **更新技能**：检查并更新现有的skill到最新版本
- **卸载技能**：移除不需要的skill
- **搜索技能**：在skillhub中搜索新的skill
- **配置管理**：查看和修改skill的配置

## 工作流程

### 列出技能

运行以下命令查看所有已安装的skill：

```bash
skillhub list
```

### 安装技能

从skillhub安装新的skill：

```bash
skillhub install <skill-name>
```

### 更新技能

更新所有已安装的skill或特定skill：

```bash
# 更新所有skill
skillhub update

# 更新特定skill
skillhub update <skill-name>
```

### 卸载技能

移除不需要的skill：

```bash
skillhub uninstall <skill-name>
```

### 搜索技能

在skillhub中搜索新的skill：

```bash
skillhub search <query>
```

### 配置管理

查看和修改skill的配置：

```bash
# 查看配置
skillhub config <skill-name>

# 修改配置
skillhub config <skill-name> <key> <value>
```

## 使用示例

1. **列出所有技能**：
   - 输入："列出所有已安装的skill"
   - 操作：运行 `skillhub list` 并展示结果

2. **安装新技能**：
   - 输入："安装一个代码审查的skill"
   - 操作：运行 `skillhub search code review`，展示结果，然后安装用户选择的skill

3. **更新技能**：
   - 输入："更新所有skill"
   - 操作：运行 `skillhub update` 并展示更新结果

4. **卸载技能**：
   - 输入："卸载不需要的skill"
   - 操作：运行 `skillhub list`，用户选择要卸载的skill，然后运行 `skillhub uninstall <skill-name>`

5. **搜索技能**：
   - 输入："搜索与前端开发相关的skill"
   - 操作：运行 `skillhub search frontend` 并展示结果

6. **管理配置**：
   - 输入："查看skill的配置"
   - 操作：运行 `skillhub config <skill-name>` 并展示配置信息

## 注意事项

- 确保skillhub命令可用且已正确安装
- 对于网络问题，会自动尝试使用clawhub作为备选
- 安装前会检查技能的安全性和兼容性
- 配置修改时会备份原始配置，以便恢复

---

## 标准工作流

### Step 1: 检测 skillhub 可用性

**CHECKPOINT**: `skillhub` 命令是否可用？
- 验证：运行 `which skillhub` 或 `skillhub --version`
- 可用：继续
- 不可用：尝试 `clawhub` 作为备选；两者都不可用时通知用户

### Step 2: 执行操作

根据用户需求选择对应命令：

#### 操作 A: 列出技能

```bash
skillhub list
```

**CHECKPOINT**: 是否获得有意义的输出？
- 成功：展示列表，包含每个 skill 的名称、版本、状态
- 失败：如果输出为空，提示"尚未安装任何 skill"或检查 skillhub 配置

#### 操作 B: 搜索并安装技能

```bash
# 先搜索
skillhub search <关键词>

# 再安装
skillhub install <skill-name>
```

**CHECKPOINT**: 安装前安全检查
- [ ] skill 名称格式正确（kebab-case）
- [ ] 来源可信（skillhub 官方仓库）
- [ ] 无已知安全漏洞
- [ ] 与当前环境兼容

#### 操作 C: 更新技能

```bash
# 更新所有
skillhub update

# 或更新特定
skillhub update <skill-name>
```

**CHECKPOINT**: 更新前备份
- 保存当前 skill 的 SKILL.md 内容作为备份
- 更新后验证 skill 仍正常工作

#### 操作 D: 卸载技能

```bash
# 先列出确认
skillhub list | grep <关键词>

# 确认后卸载
skillhub uninstall <skill-name>
```

**CHECKPOINT**: 卸载前确认
- 确认 skill 名称正确（避免误删）
- 确认 skill 不再被其他技能依赖
- 保留配置文件（如有）

#### 操作 E: 配置管理

```bash
# 查看配置
skillhub config <skill-name>

# 修改配置
skillhub config <skill-name> <key> <value>
```

**CHECKPOINT**: 配置修改前备份
- [ ] 保存当前配置文件内容
- [ ] 修改后验证配置格式正确
- [ ] 验证 skill 在新配置下正常工作

### Step 3: 验证结果

**CHECKPOINT**: 操作是否成功？
- 检查命令退出码（应为 0）
- 检查输出是否包含成功标识（如 "安装完成"、"更新成功"）
- 执行简单测试验证 skill 可用

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| skillhub 命令不存在 | skillhub 未安装或 PATH 不正确 | 尝试 `clawhub`；两者都不可用时告知用户如何安装 |
| 搜索无结果 | 关键词不匹配或仓库中无对应 skill | 建议用户尝试不同关键词，或用更通用的词 |
| 安装失败 | 网络问题、权限不足、版本冲突 | 检查网络；检查磁盘空间；尝试指定版本号；重试 |
| 更新失败 | skill 已修改导致冲突；网络问题 | 提示用户手动恢复备份；如果是自定义修改，保留本地变更 |
| 卸载失败 | skill 正在使用中；权限不足 | 等待会话结束后重试；检查并修复文件权限 |
| 配置修改失败 | 配置文件被锁定；格式错误 | 从备份恢复；手动检查配置文件语法 |
| 返回码非 0 | 未知错误 | 查看详细错误输出；运行 `skillhub --help` 获取帮助 |

### 失败时的用户通知

当 skill 管理操作失败时，**明确告知用户**：

**示例**：
```
❌ 安装 skill: code-review 失败

原因：
- skillhub 返回错误："repository not reachable"
- 可能原因：网络连接中断

建议：
1. 检查网络连接
2. 尝试使用备选源：clawhub install code-review
3. 稍后重试

要我尝试 clawhub 备选方案吗？
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 未经确认直接卸载 | 可能误删用户重要 skill | 先列出 skill 列表，让用户选择确认 |
| ❌ 不备份直接修改配置 | 可能导致 skill 不可用 | 修改前备份配置文件 |
| ❌ 不验证直接安装 | 可能安装恶意或不兼容的 skill | 安装前检查安全性和兼容性 |
| ❌ 忽略错误输出 | 无法诊断问题根源 | 捕获并展示完整错误输出 |
| ❌ 覆盖本地修改 | 用户可能有自定义的 skill 修改 | 更新前检查 diff，保留本地变更 |
| ❌ 用 sudo 强制安装 | 可能导致权限问题或安全风险 | 检查是否有无需 sudo 的替代方案 |

### 错误示例（反例）

**❌ 错误示例 1：不确认直接卸载**

```
用户：卸载不需要的 skill
执行：skillhub uninstall foo
（无任何确认）
结果：误删了用户正在使用的 skill
```

**✅ 正确做法**：

```
用户：卸载不需要的 skill
执行：
1. skillhub list 展示所有 skill
2. 询问用户要卸载哪些
3. 确认后执行 skillhub uninstall
4. 告知卸载结果
```

---

**❌ 错误示例 2：不验证直接安装**

```
用户：安装代码审查 skill
执行：skillhub install random-skill
（无任何检查）
结果：安装了恶意或不兼容的 skill
```

**✅ 正确做法**：

```
用户：安装代码审查 skill
执行：
1. skillhub search code review
2. 展示搜索结果，让用户选择
3. 检查所选 skill 的元数据（作者、版本、最后更新时间）
4. 确认用户后才 skillhub install
```

---

**❌ 错误示例 3：不备份直接修改配置**

```
执行：skillhub config my-skill key value
（无备份）
结果：配置格式错误导致 skill 不可用
```

**✅ 正确做法**：

```
执行：
1. 先读取当前配置并备份
2. skillhub config my-skill key value
3. 验证 skill 在新配置下是否正常（读取 SKILL.md，检查格式）
4. 如果有问题，从备份恢复
```

---

## FAQ 常见问题

**Q: skillhub 和 clawhub 有什么区别？**
A: skillhub 是主要的 skill 包管理器，clawhub 是备选/兼容实现。优先使用 skillhub，失败时尝试 clawhub。

**Q: 如何查看已安装的 skill 版本？**
A: 运行 `skillhub list` 或 `skillhub info <skill-name>` 查看详细信息，包括版本号。

**Q: 安装失败时如何重试？**
A: 先检查网络和磁盘空间，然后重试。可以指定版本号：`skillhub install <skill-name>@<version>`。

**Q: 如何更新所有 skill 而不中断工作？**
A: `skillhub update` 会自动处理更新。但建议在非关键任务期间执行，更新后快速验证每个 skill 的可用性。

**Q: 卸载后 skill 的配置文件怎么办？**
A: 默认会保留配置文件。如需完全删除，手动删除配置目录（通常在 `~/.config/skillhub/`）。

**Q: 如何搜索 skillhub 仓库？**
A: `skillhub search <关键词>`。支持模糊匹配，可以用多个关键词组合搜索。

**Q: 能安装本地目录作为 skill 吗？**
A: 可以：`skillhub install /path/to/local/skill` 或直接将目录放入 skills 目录。

**Q: 如何知道哪些 skill 有更新？**
A: `skillhub list --outdated` 列出有新版本的 skill。或定期运行 `skillhub update --dry-run` 预览更新。

**Q: skill 配置格式错误怎么办？**
A: skillhub 通常会在启动时验证配置。如果格式错误，会给出提示。从备份恢复，或手动修复 YAML/JSON 格式。

**Q: 可以同时安装多个版本的同一个 skill 吗？**
A: 大多数包管理器不支持。如果需要特定版本，使用 `skillhub install <skill-name>@<version>`。