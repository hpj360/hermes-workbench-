# Hermes Workbench Dashboard — 技术架构设计

> 日期：2026-07-24
> 状态：已确认，待实施
> 范围：前后端集成、API 增强、静态文件服务

---

## 1. 现有架构分析

### 1.1 分层结构

```
┌─────────────────────────────────────────────────┐
│  HTTP Server (server.py)                         │  ← 21 路由，无状态适配器
│  BaseHTTPRequestHandler + ThreadingHTTPServer     │
├─────────────────────────────────────────────────┤
│  Service Factories (cli.py)                      │  ← 服务工厂中心
│  _make_runner / _make_memory / _make_store /     │
│  _make_registry / _make_scheduler                │
├─────────────────────────────────────────────────┤
│  Domain Services                                  │  ← 业务逻辑层
│  SkillRunner / MemoryService / TaskStore /       │
│  AgentLoop / TaskScheduler / UnifiedRegistry     │
├─────────────────────────────────────────────────┤
│  Persistence (persistence.py)                    │  ← 原子文件持久化
│  atomic_write_json / atomic_append_jsonl /        │
│  safe_read_json + fcntl.flock                     │
└─────────────────────────────────────────────────┘
```

### 1.2 现有能力盘点

| 能力 | 已有 | 缺失 |
|------|------|------|
| 技能发现 | `SkillRunner.discover()` → 列表 | 列表 API 不返回 requires_bins |
| 技能执行 | `SkillRunner.run(name, args)` | 无 `POST /skills/:name/run` 端点 |
| 事件查询 | `MemoryService.list_episodes(kind, limit)` | API 不传 limit 参数 |
| 画像读取 | `MemoryService.get_user_profile()` | 无 `PUT /memory/profile` |
| 画像保存 | `MemoryService.save_user_profile()` | 无对应 API 端点 |
| 健康检查 | `GET /health` → `{status, services}` | 无 providers/skills 就绪信息 |
| 静态服务 | 无 | 需托管 prototype/index.html |

**关键发现**：Domain 层能力已齐全，只需 HTTP 层适配 + 静态服务。

---

## 2. 技术架构设计

### 2.1 改动范围

```
server.py     ← 主要改动：新增 3 端点 + 增强 3 端点 + 静态服务
index.html    ← 切换 DEMO_MODE=false + 适配真实 API 响应格式
tests/        ← 新增测试覆盖
```

### 2.2 服务边界

```
┌─ HTTP Layer (server.py) ──────────────────────────────┐
│  职责：路由分发、认证、JSON 序列化、静态文件服务          │
│  禁止：业务逻辑、状态管理                                │
├─ Service Factory Layer (cli.py) ──────────────────────┤
│  职责：依赖注入、配置管理                                │
│  禁止：HTTP 语义                                        │
├─ Domain Layer (skill_runner/memory/agent_loop) ───────┤
│  职责：业务规则、数据持久化                              │
│  禁止：HTTP 耦合                                        │
└────────────────────────────────────────────────────────┘
```

### 2.3 API 增强清单

| 端点 | 改动 | 说明 |
|------|------|------|
| `GET /health` | 增强 | 返回 providers、skills_count、skills_ready |
| `GET /skills` | 增强 | 每个 skill 增加 requires_bins、requires_env、status |
| `GET /skills/:name` | 增强 | 增加 requires_env |
| `GET /memory/episodes` | 增强 | 支持 `?limit=N` 查询参数 |
| `POST /skills/:name/run` | 新增 | 调用 `SkillRunner.run()`，返回 RunResult |
| `PUT /memory/profile` | 新增 | 调用 `MemoryService.save_user_profile()` |
| `GET /` | 新增 | 返回 prototype/index.html |
| `GET /static/*` | 新增 | 静态资源 fallback |

### 2.4 静态文件服务设计

```python
# server.py 静态服务逻辑
_PROTOYPE_DIR = Path(__file__).parent.parent.parent.parent / "prototype"

def _serve_static(self, path: str):
    """Serve static files from prototype/ directory."""
    if path == "/" or path == "/index.html":
        file_path = _PROTOTYPE_DIR / "index.html"
    else:
        file_path = _PROTOTYPE_DIR / path.lstrip("/")
    if file_path.exists() and file_path.is_file():
        # serve with correct content-type
        ...
    else:
        self._send_json(404, {"error": "not found"})
```

### 2.5 认证策略

- `/health` 和 `/`（静态首页）豁免认证
- 其他 API 端点保持现有 Bearer token 认证
- 前端 localStorage 存储 token，每次请求附加 `Authorization: Bearer`

### 2.6 前端 API 对接适配

前端 `api()` 函数需适配真实 API 响应格式：

| 页面 | API 响应 | 前端处理 |
|------|---------|---------|
| Overview | `GET /health` → `{status, providers, skills_total, skills_ready}` | 更新统计卡片 |
| Skills | `GET /skills` → `{skills: [{name, runtime, status, ...}]}` | 渲染卡片 |
| Memory | `GET /memory/facts` → `{facts: [{key, value}]}` | 渲染列表 |
| Tasks | `GET /tasks` → `{tasks: [...]}` | 渲染任务卡片 |
| Registry | `GET /registry/sources` → `{sources, total}` | 渲染源卡片 |

---

## 3. 对抗性评审

### 3.1 安全风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 静态文件路径穿越 | 高 | 限制在 prototype/ 目录内，禁止 `..` |
| Skill 执行注入 | 中 | SkillRunner 已在子进程中执行，args 经列表传递非 shell |
| Profile 写入越权 | 中 | 已有 Bearer token 认证保护 |

### 3.2 性能风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| `GET /skills` 每次 discover 全盘扫描 | 中 | 可接受，skill 数量 <100；后续可加缓存 |
| 静态文件无缓存头 | 低 | 添加 `Cache-Control` |
| index.html 1950 行单文件 | 低 | 可接受，原型阶段不需要拆分 |

### 3.3 兼容性风险

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| /health 响应结构变更破坏现有消费者 | 低 | 向后兼容：保留原有字段，仅新增字段 |
| /skills 列表新增字段 | 低 | 纯增量，不破坏现有消费者 |
| 前端 DEMO_MODE 切换 | 低 | 保留 fallback，API 不可用时回退 mock |

### 3.4 评审结论

**通过**。改动范围小、向后兼容、安全风险可控。主要工作量在 server.py 增强 + 前端适配 + 测试覆盖。
