# Hermes Workbench — 个人 OS 工作台产品设计

> 日期：2026-07-24
> 状态：已确认，待实施
> 范围：完整三阶段产品方案 + Phase 1 可交互原型

---

## 1. 产品愿景

### 1.1 定位

Hermes Workbench 是**个人 AI 工作台操作系统**。将分散在多个项目中的 skills、记忆、用户档案统一管理，逐步演进为可编排、可自动化、可跨项目调度的个人 AI 操控台。

### 1.2 三阶段路线图

| 阶段 | 核心价值 | 交付物 |
|------|---------|--------|
| **Phase 1 · 统一管理** | 跨项目中心化管理 skills/记忆/档案 | 6 页可交互 Dashboard |
| **Phase 2 · 编排自动化** | 可视化组合 skills 成工作流，自动触发执行 | 编排画布 + 任务监控面板 |
| **Phase 3 · 多项目调度** | 多项目接入、跨项目调度、资产同步合并 | 项目接入管理 + 统一调度中心 |

### 1.3 演进关系

```
Phase 1 (单项目管理)     →   Phase 2 (单项目编排)    →   Phase 3 (多项目调度)
基础管理                      自动化编排                    多项目调度中心
```

每个阶段在前一阶段基础上叠加能力，不推翻已有功能。

---

## 2. 信息架构

### 2.1 整体布局

```
┌──────────────────────────────────────────────────────┐
│  ◈ Hermes Workbench    ● 已连接    ⌘K    ⚙ 用户画像 │  ← Top Bar
├───────────┬──────────────────────────────────────────┤
│           │                                          │
│  Phase 1  │                                          │
│ ◈ 概览    │         [页面内容区]                      │
│ ▤ 技能    │                                          │
│ ⚡ 记忆    │   - hash 路由切换                        │
│ ☑ 任务    │   - 每页独立 fetch 对应 API               │
│ 🔗 注册中心│   - 加载态/空态/错误态/数据态             │
│           │                                          │
│ ────────  │                                          │
│  Phase 2  │                                          │
│ 🔀 编排自动化  (灰显 · 即将推出)                │
│           │                                          │
│ ────────  │                                          │
│  Phase 3  │                                          │
│ 📡 项目调度中心    (灰显 · 即将推出)                │
│           │                                          │
├───────────┴──────────────────────────────────────────┤
│  v0.2.0 · 33 技能 · 2 提供商 · ████░░░░ 60%    │  ← Status Bar
└──────────────────────────────────────────────────────┘
```

### 2.2 路由表

| Hash 路由 | 页面 | API 调用 |
|-----------|------|---------|
| `#/overview` | 概览仪表盘 | `GET /health` + `GET /registry/summary` + `GET /memory/episodes?limit=5` |
| `#/skills` | 技能管理 | `GET /skills` |
| `#/skills/:name` | 技能详情 | `GET /skills/:name` |
| `#/memory` | 记忆管理 | `GET /memory/facts` + `GET /memory/episodes` |
| `#/tasks` | 任务管理 | `GET /tasks` |
| `#/tasks/:id` | 任务详情 | `GET /tasks/:id` |
| `#/registry` | 注册中心 | `GET /registry/sources` + `GET /registry/skills` + `GET /registry/agents` + `GET /registry/knowledge` |
| `#/profile` | 用户画像 | `GET /memory/profile` |

### 2.3 交互模式

- **导航**：点击侧边栏 → 更新 `location.hash` → JS 路由分发 → 渲染对应页面
- **数据加载**：进入页面时 `fetch()` 对应 API，显示骨架屏 → 数据/空态/错误态
- **全局命令**：`⌘K` 弹出命令面板（Phase 1 仅快速跳转）
- **实时状态**：Top Bar 的连接状态每 30s 轮询 `/health`
- **认证**：若 API 返回 401，弹出 token 输入框，存入 localStorage

### 2.4 视觉规范（科技暗黑）

| 元素 | 规格 |
|------|------|
| 背景 | `#080809` 主背景，`rgba(255,255,255,0.03)` 卡片 |
| 边框 | `rgba(255,255,255,0.08)` |
| 主色 | `#6366f1 → #8b5cf6` 渐变 |
| 文字 | `#e0e0e0` 主文字，`#8b8b8b` 次文字 |
| 圆角 | 卡片 `12px`，按钮 `8px`，标签 `999px` |
| 毛玻璃 | `backdrop-filter: blur(8px)` + `rgba` 半透明 |
| 强调发光 | `box-shadow: 0 0 20px rgba(99,102,241,0.15)` |

---

## 3. Phase 1 · 统一管理（详细设计）

### 3.1 概览 · 概览仪表盘

**布局**：顶部 4 个统计卡片 + 左下健康状态面板 + 右下最近活动流

**统计卡片**：
- 技能总数（`GET /registry/summary` → `skills_count`）
- API 路由数（21）
- 记忆层数（3）
- 已配置 Providers 数（`GET /health` → `providers`）

**健康状态面板**：
- API 在线状态（●/✗）
- 技能就绪率（33/33 就绪 或 27/33 就绪, 6 缺失依赖）
- 记忆层级状态（L1+L2+L3 active）
- 已配置 Providers 列表

**最近活动流**：
- 最近 5 条 L2 episodes（`GET /memory/episodes?limit=5`）
- 每条显示：时间、类型（loop/fact/task）、摘要、状态

**交互**：刷新按钮手动刷新；统计卡片可点击跳转到对应页面

### 3.2 技能 · 技能管理

**列表视图**：
- 搜索框（实时过滤名称/描述）
- 状态过滤器（全部 / 就绪 / 缺失）
- 每个 skill 一张卡片：名称、状态标签（就绪=绿/缺失=红）、runtime（提示词/Python/Shell/Node）、requires 摘要

**详情视图**（点击 skill 展开）：
- 完整元数据：name、description、runtime、requires_bins、requires_env、path、entrypoint
- 运行面板：参数输入框 + 执行按钮 + 输出区域
- 运行需要后端 `POST /skills/:name/run` 端点（Phase 1 原型中用 mock 模拟）

**数据源**：`GET /skills` → 列表；`GET /skills/:name` → 详情

### 3.3 记忆 · 记忆管理

**Tab 切换三种记忆层级**：

**事实 (L1)**：
- 列表展示所有 facts：key + value 预览 + 删除按钮
- 新建 fact 表单：key 输入 + value 文本域 + 提交
- API：`GET /memory/facts`、`POST /memory/facts`、`DELETE /memory/facts/:key`

**事件 (L2)**：
- 时间倒序列表，每条：图标（🔄loop/📝fact/📋task）、时间、摘要、详情展开
- 按 kind 过滤（全部/loop/fact/task）
- API：`GET /memory/episodes`

**画像 (L3)**：
- 只读 JSON 展示（编辑在用户画像页）
- API：`GET /memory/profile`

### 3.4 任务 · 任务管理

**任务列表**：
- 每个任务一张卡片：task_id、mode（单次/循环）、状态色标、步骤链（alpha→beta→gamma）、创建时间
- 操作按钮：详情、重跑、取消（仅运行中）

**新建任务面板**：
- 动态步骤构建器：每步选择 skill + 输入 args + 添加步骤按钮
- 模式选择：单次 / 循环
- 循环参数：interval（秒）、max_runs
- 创建并运行按钮

**任务详情**：
- 基本信息 + 每轮执行结果（rounds 数组）
- 每轮：ok 状态、步骤结果列表、耗时、错误信息
- API：`GET /tasks`、`POST /tasks`、`GET /tasks/:id`、`POST /tasks/:id/run`、`POST /tasks/:id/cancel`

### 3.5 注册中心 · 注册中心

**Tab 切换四个视图**：

**数据源**：注册源卡片（名称、类型 filesystem/github、skills 数量、agents 数量、在线状态）

**技能**：跨源对照表（skill 名称 × 源 → ✓/✗），快速发现哪些 skill 只在某源存在

**智能体**：跨源 agent 列表

**知识文档**：跨源知识文档列表

**API**：`GET /registry/sources`、`GET /registry/skills`、`GET /registry/agents`、`GET /registry/knowledge`

### 3.6 用户画像 · 用户画像

- 默认只读 JSON 展示（语法高亮）
- 编辑模式：JSON 编辑器 + 字段说明
- 保存按钮调用 API 更新
- API：`GET /memory/profile`

---

## 4. Phase 2 · 编排自动化（概念设计）

### 4.1 编排画布

- 可视化 DAG 编辑器：拖拽 skill 节点，连线形成工作流
- 每个节点显示：skill 名称、runtime、状态
- 支持条件分支（if/else 节点）
- 支持并行执行（多个下游节点）

### 4.2 触发器管理

| 触发器 | 说明 |
|--------|------|
| GitHub Issue | label 匹配（如 `workbench`）自动拉取执行 |
| 定时 | cron 表达式，支持工作日/自定义周期 |
| Webhook | 外部系统 POST 触发，支持认证 token |

### 4.3 执行监控

- 实时查看工作流执行进度：每步状态（✓/⏳/✗/⏭）
- 每步输出预览（stdout 前 500 字符）
- 失败重试配置（自动重试 N 次 + 退避策略）
- 执行历史时间线

### 4.4 技术复用

Phase 2 复用 Phase 1 的 AgentLoop + TaskScheduler：
- 工作流 = LoopStep 列表（已有数据结构）
- 触发器 = TaskScheduler + cron/ webhook 扩展
- 执行监控 = LoopResult + rounds 已有结构

---

## 5. Phase 3 · 多项目调度（概念设计）

### 5.1 核心定义

Phase 3 是**多项目接入与调度中心**，不是简单的对话界面。三大核心能力：项目接入管理、跨项目调度、资产同步合并。

### 5.2 项目接入管理

| 操作 | 说明 |
|------|------|
| 接入项目 | 输入 Git 仓库地址或 API URL → 自动发现 skills/agents/知识文档 |
| 项目状态 | 在线/离线/同步中，skills 数量，agents 数量，最近活动 |
| 断开/移除 | 安全断开项目连接，保留本地缓存 |
| 权限配置 | 每个项目可配置 API token、同步方向（单向/双向） |

### 5.3 跨项目调度

| 能力 | 说明 |
|------|------|
| 技能路由 | 同一任务可路由到不同项目执行（按负载/能力/可用性选择） |
| 跨项目编排 | Skill A (项目1) → Skill B (项目2) 的跨项目工作流 |
| 负载均衡 | 多个项目都有同一 skill 时，自动选择空闲节点执行 |
| 故障转移 | 项目 A 超时 → 自动切换到项目 B 重试 |
| 统一队列 | 所有项目的任务统一排队，按优先级调度 |

### 5.4 资产同步与合并

| 能力 | 说明 |
|------|------|
| Skills 同步 | 将项目 A 的新 skill 推送到项目 B，或反向拉取 |
| 记忆合并 | 跨项目的 L1 facts / L2 episodes 合并到统一视图 |
| 用户画像统一 | 多项目的 profile 合并为一个全局画像 |
| 知识文档同步 | 跨项目共享知识文档 |

### 5.5 布局概念

```
┌──────────────────────────────────────────────────────────┐
│  ◈ Hermes Workbench                  [⌘K]          ⚙   │
├───────────┬────────────────────────┬─────────────────────┤
│           │  ── 接入项目 ──         │  调度面板            │
│ Phase 1   │  ┌──────────┐ ┌──────┐ │                     │
│ Phase 2   │  │ ● hpj360 │ │ ● ai │ │  活跃调度:           │
│ Phase 3   │  │  33 sks  │ │  12  │ │  ┌────────────────┐ │
│ 📡 项目调度中心 ●│  └──────────┘ └──────┘ │  │ #001 hpj360    │ │
│           │  ┌──────────┐ ┌──────┐ │  │ weather→summar │ │
│           │  │ + 接入    │ │ ○loc │ │  │ ⏳ running     │ │
│           │  └──────────┘ └──────┘ │  └────────────────┘ │
│           │  ── 跨项目操作 ──       │  队列: #002 #003     │
│           │  [同步技能] [同步记忆] │  策略: 负载均衡       │
├───────────┴────────────────────────┴─────────────────────┤
│  3 项目 · 2 活跃 · 78 技能 · 5 智能体           │
└──────────────────────────────────────────────────────────┘
```

---

## 6. 技术架构

### 6.1 文件结构

```
prototype/
├── index.html          ← 主文件（单 HTML，~800行）
│   ├── <style>         ← 所有 CSS（科技暗黑主题）
│   ├── <body>          ← HTML 骨架（sidebar + content + statusbar）
│   └── <script>        ← JS 路由 + API 封装 + 页面渲染
└── style-samples.html  ← 风格对比页（已完成）
```

### 6.2 JS 模块划分（单文件内）

```
┌─ Router ──────────────────────────────────────┐
│  hashchange → parse route → render page       │
├─ API Client ──────────────────────────────────┤
│  fetch wrapper + auth header + error handling │
├─ Pages ───────────────────────────────────────┤
│  renderOverview() / renderSkills() / ...      │
├─ Components ──────────────────────────────────┤
│  Card / List / Badge / Modal / Skeleton       │
├─ State ───────────────────────────────────────┤
│  token (localStorage) / cache / loading       │
└───────────────────────────────────────────────┘
```

### 6.3 API 对接策略

| 策略 | 说明 |
|------|------|
| baseURL | 同源（`/`），原型由 `hermes workbench serve` 托管 |
| 认证 | 读取 localStorage 的 token，附加 `Authorization: Bearer` |
| 降级 | API 不可用时显示 Mock 数据（内置），标注 `[演示模式]` |
| 轮询 | Overview 页每 30s 刷新 health；Tasks 页每 5s 刷新运行中任务 |
| 错误处理 | 401 → 弹出 token 输入；404 → 空态；500 → 错误卡片 |

### 6.4 Mock 数据模式

原型需独立于后端运行。所有 API 调用有 fallback：

```javascript
async function api(path) {
  try {
    const res = await fetch(path, { headers: authHeaders() });
    if (!res.ok) throw res;
    return await res.json();
  } catch (e) {
    return MOCK_DATA[path] ?? { error: 'offline', demo: true };
  }
}
```

API 不可用时自动回退到内置 mock 数据，页面左上角显示 `[演示模式]` 标记。

### 6.5 部署方式

1. **独立预览**：`python -m http.server` 在 prototype/ 目录启动
2. **集成部署**：将 index.html 挂载到 `server.py` 的 `GET /` 路由（后续迭代）
3. **Docker**：已有的 Dockerfile 直接可用，EXPOSE 8000

---

## 7. 成功标准

| 指标 | Phase 1 原型 | 验证方式 |
|------|-------------|---------|
| 6 个页面全部可交互 | 概览/技能/记忆/任务/注册中心/用户画像 | 逐页点击验证 |
| 连接真实 API | 启动 `hermes workbench serve` 后数据实时加载 | 启动 server + 打开原型 |
| 独立运行 | 无 server 时使用 mock 数据正常展示 | 断开 server 验证 |
| 科技暗黑风格 | 毛玻璃/渐变/深色基调一致 | 视觉检查 |
| 响应式 | 1280px+ 正常，768px+ 可用 | 缩放浏览器验证 |
| Phase 2/3 概念展示 | 侧边栏灰显入口 + 即将推出面板 | 点击验证 |
