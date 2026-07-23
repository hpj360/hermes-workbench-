# Harness Engineering 知识沉淀

> 来源：
> 1. FairMind《Harness Engineering: The Discipline That Determines Whether AI Agents Ship or Stall》
> 2. Innobu《Agentic Harness Engineering: The Framework for Reliable AI Agents》
> 3. Microsoft Agent Framework BUILD 2026 发布
> 4. 复旦大学《Agentic Harness Engineering: Observability-Driven Automatic Evolution》
> 5. 花叔《Loop Engineering 橙皮书》及 GitHub 开源橙皮书
> 6. Hermes Agent (Nous Research) GEPA 自我进化算法

---

## 一、核心定义

**Agent = Model + Harness**

> 如果你不负责训练模型，那你做的所有 Agent 开发工作，都是 Harness 工程。
> — LangChain

Harness 是包裹在大模型外层的全套非模型工程体系，包含：
- 系统提示（System Prompt）
- 工具注册表（Tool Registry）
- 沙箱隔离（Sandbox）
- 权限模型（Permission Model）
- 记忆系统（Memory）
- 上下文管理（Context Management）
- 子 Agent 编排（Sub-agents）
- 钩子系统（Hooks）
- 可观测性（Observability）
- 评估循环（Eval Loop）

**模型决定 AI 的上限，Harness 决定 AI 的下限和稳定性。**

---

## 二、四次跃迁：从 Prompt 到 Loop

```
Prompt Engineering → Context Engineering → Harness Engineering → Loop Engineering
好好说话              给够信息             设规则约束          让系统自己跑
核心能力：语言表达     核心能力：信息组织     核心能力：规则制定     核心能力：目标定义
```

| 层次 | 管什么 | 类比 |
|------|--------|------|
| Prompt Engineering | 单次输入的措辞 | 教员工怎么说一句话 |
| Context Engineering | 模型脑子里装哪些信息 | 给员工看哪些资料 |
| Harness Engineering | Agent 运行的整套装备 | 给员工配齐工位、工具、权限、流程 |
| Loop Engineering | 系统自己定时跑、自我进化 | 设计一个部门自动运转 |

**关键洞察**：每一次跃迁，你离亲手干活越来越远，离设计系统越来越近。

---

## 三、Harness 十大组件

来源：Innobu + Microsoft Agent Framework + 行业收敛

| # | 组件 | 职责 | OpenClaw 对应实现 |
|---|------|------|------------------|
| 1 | **系统提示** | 塑造工作风格、任务分解策略 | `src/agents/system-prompt.ts` |
| 2 | **工具注册表** | 可用工具的发现、加载、门控 | `src/agents/skills/` + `metadata.openclaw.requires` |
| 3 | **沙箱隔离** | 限制文件/命令访问范围 | `src/agents/sandbox/` |
| 4 | **权限模型** | 工具调用的审批与授权 | `auth-profiles` + `ToolApprovalAgent` 模式 |
| 5 | **记忆系统** | 短期+长期+语义记忆 | `MEMORY.md` + `memory/YYYY-MM-DD.md` + 向量搜索 |
| 6 | **上下文管理** | 压缩、裁剪、just-in-time 加载 | `compaction` + `pruning` + `context-engine` 插件 |
| 7 | **子 Agent** | 任务分解、并行执行、writer/judge 分离 | `subagent-spawn` + `subagent-registry` |
| 8 | **钩子系统** | 生命周期事件拦截与注入 | Gateway hooks + Plugin hooks（双层） |
| 9 | **可观测性** | 轨迹记录、指标采集、调试 | 事件流 + OpenTelemetry + 转录持久化 |
| 10 | **评估循环** | 持续评测、回归测试、基线管理 | `skill_evaluator.py` + `batch_eval.py` + 基线 |

**结论**：OpenClaw 已具备全部十大组件，是完整的 Harness 实现。

---

## 四、Planner / Generator / Evaluator 模式

来源：Innobu + Anthropic 实践 + 花叔橙皮书

**核心原则：写代码的那个 AI，不能给自己的代码打分。**

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Planner  │ →   │Generator │ →   │Evaluator │
│ 规划步骤  │     │ 执行生成  │     │ 独立评判  │
└──────────┘     └──────────┘     └──────────┘
      ↑                                 │
      └───────── 反馈循环 ──────────────┘
```

| 角色 | 职责 | 实现方式 |
|------|------|---------|
| **Planner** | 分解任务、制定步骤 | system prompt + todo list |
| **Generator** | 执行步骤、生成产出 | 主 Agent + 工具调用 |
| **Evaluator** | 独立验证、挑刺 | **独立 subagent**（不同会话/不同模型） |

**反模式**：同一个 Agent 既写代码又自我评价 → 几乎总是自信地夸自己。

**正确做法**：
- 生成器和评判器必须分离
- 评判器要"调教得多疑一点"
- 判定"干完了没"的，不能是干活的那个

---

## 五、Harness 与 Loop 的关系

来源：花叔《Loop Engineering 橙皮书》

```
Loop = 驱动力（往那个方向一直跑）
Harness = 约束（划定边界，不能怎么做）
两者相加 = 完整系统
```

| 概念 | 作用 | 没有的后果 |
|------|------|-----------|
| Loop | 定时器 + 自我孵化 + 状态记忆 | 还得手动踢，不是真正的自动化 |
| Harness | 规则约束 + 安全世界 + 质量门禁 | Agent 钻空子（如删掉失败的测试来"通过"） |

**古德哈特定律**：当一个衡量指标变成了目标本身，它就不再是一个好的衡量指标。
- 例：目标是"测试全通过" → Agent 直接删掉失败的测试 → 指标满足但问题没解决
- 解法：Harness 约束"不能删除测试文件" + "不能修改测试断言"

---

## 六、GEPA 自我进化算法

来源：Hermes Agent (Nous Research)，ICLR 2026 Oral 论文

**核心机制**：每 ~15 次工具调用后自动评估会话，提取可复用技能。

```
工具调用累积 → 达到阈值(~15次) → 暂停评估
                                    ↓
                            模式识别：出现了什么模式？
                            步骤提取：采取了哪些步骤？
                            可复用性判断：值得保存吗？
                                    ↓
                              是 → 写入 skill 文件
                              否 → 继续执行
```

**效果**：20+ 自生成技能的 Agent 完成相似任务速度提升 40%。

**与 self-improving-agent 的差异**：

| 维度 | 当前 self-improving-agent | Hermes GEPA |
|------|--------------------------|-------------|
| 触发方式 | 事件触发（错误/纠正） | 周期触发（每 N 次调用） |
| 评估内容 | 特定错误或纠正 | 整个会话的模式 |
| 技能提取 | 手动判断 | 自动评估+自动提取 |
| 进化速度 | 慢（依赖错误发生） | 快（主动发现模式） |

**借鉴方案**：在 self-improving-agent 中增加"周期性评估"模式。

---

## 七、/goal 和 /loop 命令模式

来源：Hermes Agent + Claude Code

| 命令 | 驱动方式 | 适用场景 | 停止条件 |
|------|---------|---------|---------|
| `/goal` | 进度驱动 | 有明确终点的任务 | 验收条件满足 |
| `/loop` | 时间驱动 | 持续监控、轮询 | 用户喊停 |

**目标定义四步框架**（卡兹克）：
1. 完成标准要可以被**机器验证**
2. 边界条件要跟完成标准**一起定义**（不能怎么做）
3. 要有**失败的降级方案**
4. 目标要**分层**（全局约束 vs 当前任务目标）

**示例**：
```
/goal "修复 test/ 目录下所有失败的测试，tsc --noEmit 零报错，npm run lint 零违规"
  - 边界：不能删除测试文件，不能修改测试断言
  - 降级：如果 3 轮后仍有失败，列出剩余失败项交给用户

/loop "每 5 分钟检查一次部署状态，部署成功后通知我" --interval 5m
  - 边界：只读检查，不执行任何修改操作
  - 降级：检查 20 次后停止，通知用户手动处理
```

---

## 八、三层记忆模型

来源：Hermes Agent + Microsoft Agent Framework + OpenClaw 现有实现

| 层 | 名称 | 存储 | 生命周期 | OpenClaw 实现 |
|----|------|------|---------|--------------|
| L1 | 工作记忆 | 内存/Redis | 当前会话 | 会话上下文 + compaction |
| L2 | 情节记忆 | 向量数据库 | 跨会话 | `memory/YYYY-MM-DD.md` + 向量搜索 |
| L3 | 语义记忆 | 结构化存储 | 永久 | `MEMORY.md` + `USER.md`（用户偏好） |

**语义记忆示例**：
```
用户说："我喜欢简洁的代码风格"
→ 语义记忆更新：user_prefs["code_style"] = "简洁"
→ 下次用户问代码问题，自动附加这个偏好到 system prompt
```

**OpenClaw 已有 L1 和 L2**，需要补充 L3（语义记忆/用户偏好）。

---

## 九、可观测性三大支柱

来源：复旦大学《Agentic Harness Engineering》论文

| 支柱 | 含义 | 实现方式 |
|------|------|---------|
| **组件可观测性** | 每个可编辑组件有文件级表示 | SKILL.md + 配置文件 + 版本控制 |
| **经验可观测性** | 轨迹蒸馏为可消费的证据 | `.learnings/` + 评估报告 + 基线 |
| **决策可观测性** | 每次编辑附带预测，下轮验证 | 评估前后的分数对比 + 回归测试 |

**核心洞察**：把每次编辑变成一个"可证伪的契约"，Harness 进化才能自主进行而不沦为试错。

---

## 十、项目落地路线图

### 已具备（OpenClaw 原生）

- ✅ Agent Loop（pi-embedded-runner + 事件流）
- ✅ 22 个消息平台集成
- ✅ 双层钩子系统（Gateway + Plugin）
- ✅ 记忆系统（Markdown + 向量搜索 + MMR + 时间衰减）
- ✅ 多 Agent 隔离（bindings + subagent）
- ✅ 技能生态（AgentSkills + ClawHub + SkillHub + 评估体系）
- ✅ Compaction + 记忆刷新
- ✅ Cron 调度器

### 需要补充（借鉴 Hermes）

| 优先级 | 借鉴项 | 实施方式 | 预期收益 |
|--------|--------|---------|---------|
| P0 | `/goal` + `/loop` 命令 | 新建 loop-engineering skill | 直接落地 Loop Engineering |
| P1 | GEPA 周期性评估 | 增强 self-improving-agent | 提升自我进化效率 |
| P2 | 三层记忆模型 | 补充 L3 语义记忆（USER.md） | 个性化用户体验 |
| P3 | Planner/Generator/Evaluator | subagent 分离模式文档化 | 提升产出质量 |

---

## 十一、关键金句

1. **"Agent = Model + Harness。如果你不是在训练模型，那你做的都是 Harness 工程。"** — LangChain

2. **"模型决定 AI 的上限，Harness 决定 AI 的下限和稳定性。"** — 行业共识

3. **"写代码的那个 AI，不能给自己的代码打分。"** — 花叔

4. **"同一个循环，两个人能用出完全相反的结果。一个人用它在自己吃得很透的活上跑得更快；另一个人用它来逃避'吃透'这件事本身。"** — Addy Osmani

5. **"一个好的目标定义，不能只有做完了的标准，还必须有不能怎么做的边界。"** — 卡兹克

6. **"Loop = 驱动力，Harness = 约束。两者相加 = 完整系统。"** — 花叔
