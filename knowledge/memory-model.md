# 三层记忆模型

> 借鉴 Hermes Agent 三层记忆系统 + Microsoft Agent Framework FileMemoryProvider + OpenClaw 现有记忆架构

---

## 一、模型概览

```
┌─────────────────────────────────────────────┐
│              L3: 语义记忆                    │
│   用户偏好、事实知识、长期规则                 │
│   存储：USER.md + MEMORY.md（结构化）         │
│   生命周期：永久                              │
├─────────────────────────────────────────────┤
│              L2: 情节记忆                    │
│   历史对话摘要、任务记录、学习日志             │
│   存储：memory/YYYY-MM-DD.md + 向量搜索       │
│   生命周期：跨会话（带时间衰减）               │
├─────────────────────────────────────────────┤
│              L1: 工作记忆                    │
│   当前会话上下文、中间推理结果                 │
│   存储：会话内存 + compaction                  │
│   生命周期：当前会话                          │
└─────────────────────────────────────────────┘
```

---

## 二、各层详解

### L1: 工作记忆（Working Memory）

**职责**：维护当前会话的上下文，实时保存对话和中间推理结果。

| 属性 | 说明 |
|------|------|
| 存储 | 会话内存（pi-agent-core 上下文） |
| 生命周期 | 当前会话 |
| 容量限制 | 受 context window 限制（通常 128k-200k tokens） |
| 淘汰机制 | compaction（自动压缩旧历史为摘要） |

**OpenClaw 实现**：
- 会话上下文由 `pi-embedded-runner` 维护
- 接近 context window 时触发 compaction
- compaction 前触发"记忆刷新"（Memory Flush），将重要信息写入 L2

**最佳实践**：
- 工作记忆是易失的，重要信息必须及时写入 L2
- 不要依赖工作记忆跨会话保留信息
- compaction 后的摘要质量取决于原始对话的清晰度

### L2: 情节记忆（Episodic Memory）

**职责**：记录历史对话摘要、任务执行记录、学习日志，支持跨会话检索。

| 属性 | 说明 |
|------|------|
| 存储 | `memory/YYYY-MM-DD.md`（Markdown 文件）+ 向量索引 |
| 生命周期 | 跨会话（带时间衰减，半衰期 30 天） |
| 检索方式 | 向量相似度 + BM25 关键词（混合搜索）+ MMR 去重 |
| 索引后端 | sqlite-vec（默认）/ LanceDB / QMD / 远程嵌入 |

**OpenClaw 实现**：
- 每日记忆文件：`~/.openclaw/workspace/memory/YYYY-MM-DD.md`
- 向量搜索：`memory_search` 工具（支持混合搜索 + MMR + 时间衰减）
- 定向读取：`memory_get` 工具（按文件+行范围）

**写入时机**：
1. compaction 前的 Memory Flush（自动）
2. 用户明确要求"记住这个"
3. 重要任务完成后（主动记录）
4. GEPA 周期性评估发现可复用模式时

**最佳实践**：
- 每条记忆包含：时间、事件、结果、教训
- 避免记录敏感信息（tokens、私钥）
- 定期清理过期信息

### L3: 语义记忆（Semantic Memory）

**职责**：存储用户偏好、事实知识、长期规则，永久保留。

| 属性 | 说明 |
|------|------|
| 存储 | `USER.md`（用户偏好）+ `MEMORY.md`（策展记忆） |
| 生命周期 | 永久 |
| 加载方式 | 每次会话启动时自动注入 system prompt |

**USER.md 格式**（新增，借鉴 Hermes 语义记忆）：

```markdown
# User Profile

## 偏好
- 代码风格：简洁，偏好函数式编程
- 注释语言：中文
- 测试框架：pytest（Python）/ vitest（TypeScript）
- 包管理器：pnpm
- 编辑器：VS Code

## 工作习惯
- 喜欢先看整体架构再深入细节
- 偏好分步执行，每步确认
- 不喜欢过多的自动操作

## 项目约定
- 使用 conventional commits
- PR 必须包含测试
- 代码必须通过 lint 检查

## 常用环境
- OS: macOS
- Shell: zsh
- Node: v22
- Python: 3.12
```

**MEMORY.md 格式**（已有，OpenClaw 原生）：

```markdown
# Long-Term Memory

## 项目知识
- 项目使用 OpenClaw 作为 Agent 运行时
- 技能系统遵循 AgentSkills 规范
- 评估工具在 evals/scripts/ 目录

## 重要决策
- 2026-06: 选择 faster-whisper 替代 openai-whisper（磁盘限制）
- 2026-06: agent-browser 作为抖音提取首选方案

## 常见问题
- 微信文章需要 UA 伪装获取
- 抖音短链接需要 agent-browser 解析
```

**语义记忆更新规则**：

| 触发条件 | 更新内容 | 目标文件 |
|---------|---------|---------|
| 用户表达偏好 | 偏好项 | `USER.md` |
| 用户纠正行为 | 行为规则 | `USER.md` |
| 项目重要决策 | 决策记录 | `MEMORY.md` |
- 发现通用知识 | 事实知识 | `MEMORY.md` |
| 学习升级 | 最佳实践 | `MEMORY.md` 或 `AGENTS.md` |

---

## 三、记忆流转机制

```
用户输入
    │
    ▼
┌─────────────┐
│ L3 加载      │ ← 每次会话启动时自动注入 USER.md + MEMORY.md
│ (永久记忆)   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ L2 检索      │ ← 根据当前查询，向量搜索相关历史记忆
│ (情节记忆)   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ L1 工作      │ ← 当前会话上下文 + L3 + L2 检索结果
│ (工作记忆)   │
└──────┬──────┘
       │
       ▼
   Agent 推理 + 工具调用
       │
       ▼
┌─────────────┐
│ 写入 L2      │ ← 重要信息写入 memory/YYYY-MM-DD.md
│ (情节记忆)   │    compaction 前触发 Memory Flush
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 写入 L3      │ ← 用户偏好/重要决策写入 USER.md / MEMORY.md
│ (永久记忆)   │    需要明确判断：这个信息是否永久有用？
└─────────────┘
```

---

## 四、与 OpenClaw 的集成

### 现有实现映射

| 模型层 | OpenClaw 组件 | 状态 |
|--------|-------------|------|
| L1 工作记忆 | 会话上下文 + compaction | ✅ 已实现 |
| L2 情节记忆 | `memory/YYYY-MM-DD.md` + 向量搜索 | ✅ 已实现 |
| L3 语义记忆 | `MEMORY.md` | ⚠️ 部分实现 |
| L3 用户偏好 | `USER.md` | ❌ 需要补充 |

### 需要补充

1. **创建 USER.md 模板**：在 OpenClaw workspace 中添加 `USER.md`
2. **偏好检测机制**：在 self-improving-agent 中增加用户偏好检测
3. **偏好注入**：在 system prompt 构建时自动注入 USER.md 内容

### 配置建议

```yaml
# openclaw.yaml
agents:
  defaults:
    memory:
      flush_before_compaction: true  # 已有
      user_profile: "~/.openclaw/workspace/USER.md"  # 新增
      long_term_memory: "~/.openclaw/workspace/MEMORY.md"  # 已有
      daily_memory: "~/.openclaw/workspace/memory/"  # 已有
```

---

## 五、最佳实践

### 写入规则

| 信息类型 | 写入层 | 时机 |
|---------|--------|------|
| 当前对话上下文 | L1 | 实时（自动） |
| 任务完成摘要 | L2 | 任务完成后 |
| 错误和教训 | L2 | 错误发生时 |
| 用户偏好 | L3 | 用户表达偏好时 |
| 重要决策 | L3 | 决策确定时 |
| 通用知识 | L3 | 验证有效后 |

### 读取规则

| 场景 | 读取层 | 方式 |
|------|--------|------|
| 会话启动 | L3 | 自动注入 system prompt |
| 任务相关历史 | L2 | 向量搜索 |
| 特定日期记录 | L2 | 直接读取文件 |
| 用户偏好 | L3 | 自动注入（每次会话） |
| 当前对话 | L1 | 自动（会话上下文） |

### 清理规则

| 层 | 清理策略 |
|----|---------|
| L1 | compaction 自动清理 |
| L2 | 时间衰减（半衰期 30 天）+ 定期人工清理 |
| L3 | 永久保留，仅人工删除或更新 |

---

## 六、与 Hermes 的对比

| 维度 | Hermes Agent | OpenClaw（增强后） |
|------|-------------|-------------------|
| L1 存储 | Redis | 会话内存 |
| L2 存储 | Qdrant 向量数据库 | Markdown + sqlite-vec/LanceDB |
| L3 存储 | 结构化数据库 | USER.md + MEMORY.md |
| L3 内容 | 用户偏好、事实知识 | 同 + 项目决策、通用知识 |
| 检索方式 | 向量搜索 | 向量 + BM25 混合 + MMR |
| 时间衰减 | 无 | 30 天半衰期 |
| 多模态 | 支持 | 支持（Gemini Embedding） |

**结论**：OpenClaw 的记忆架构在 L2 层更成熟（混合搜索 + MMR + 时间衰减），只需补充 L3 的 USER.md 即可实现完整的三层模型。
