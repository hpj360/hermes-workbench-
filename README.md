# Hermes

Hermes 是一个独立于主仓库（OpenClaw/openclaw-main）的 Python Agent 层，继承主仓库中常用的账号与 API 环境配置，内置已沉淀的 24 个 skills 与 4 篇知识文档。

## 目录结构

```text
Hermes/
├── src/hermes/          # Python 包
│   ├── __init__.py
│   ├── config.py        # 环境变量加载、Settings 定义、多 provider 支持
│   ├── logging.py       # 结构化日志配置
│   ├── skills.py        # Skills/知识文档发现与管理
│   └── main.py          # CLI 入口（argparse 子命令）
├── skills/              # 从主仓库拉取的沉淀 skill（24 个）
├── knowledge/           # 从主仓库拉取的知识文档（4 篇）
├── tests/               # 单元测试
├── manifest.json        # skill / knowledge 清单
├── .state/              # Hermes 运行时状态（项目内，避免沙盒限制）
├── .cache/              # 运行时缓存
├── .env.example         # 环境变量模板（继承自主仓库）
├── pyproject.toml       # Python 项目配置
├── requirements.txt     # 运行时依赖
├── requirements-dev.txt # 开发依赖
└── README.md
```

## 环境继承说明

Hermes 的环境加载优先级如下（从高到低）：

1. 当前 shell 已导出的环境变量
2. `Hermes/.env` 文件
3. 主仓库的 `.env` 文件：
   - `/workspace/.env`
   - `/workspace/OpenClaw/openclaw-main/.env`
4. `hermes.config.Settings` 中定义的默认值

Hermes 自己的变量优先生效，通用 API Key（如 `OPENAI_API_KEY`、`SLACK_BOT_TOKEN` 等）可自动从主仓库继承。

所有用户可写状态（`.state` / `.cache` / logs）均放在项目目录内，避免写入沙盒白名单外的目录（如 `~/.xxx`）。

## 支持的 LLM Providers

| 提供商 | 环境变量 | 备注 |
|-------|---------|------|
| OpenAI | `OPENAI_API_KEY` | `OPENAI_BASE_URL` 可自定义 |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | |
| Google Gemini | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | |
| OpenRouter | `OPENROUTER_API_KEY` | OpenAI 兼容 |
| Moonshot (Kimi) | `MOONSHOT_API_KEY` | 国内 |
| 智谱 GLM / z.ai | `ZAI_API_KEY` | 国内 |
| 百度千帆 | `QIANFAN_ACCESS_KEY` + `QIANFAN_SECRET_KEY` | 国内 |
| 阿里通义千问 / Qwen | `DASHSCOPE_API_KEY` | 国内 |
| 小米 MiMo | `XIAOMI_API_KEY` | |
| MiniMax | `MINIMAX_API_KEY` | |
| Mistral AI | `MISTRAL_API_KEY` | |
| Novita AI | `NOVITA_API_KEY` | OpenAI 兼容 |
| Ollama（本地） | — | 默认 `http://localhost:11434/v1`，无需 Key |
| ModelScope 魔搭 | `MODELSCOPE_API_KEY` | OpenAI 兼容网关 |

## CLI 命令

安装后可直接使用 `hermes` 命令：

```bash
hermes start              # 启动 Hermes（默认命令）
hermes doctor             # 环境健康检查（含 skill 依赖预检）
hermes config show        # 查看当前生效配置（密钥脱敏）
hermes profile init       # 从模板初始化 profile.json
hermes profile show       # 查看用户画像
hermes skills list        # 列出所有已安装 skills
hermes knowledge list     # 列出所有知识文档
hermes workbench serve    # 启动 Dashboard HTTP API（默认 :8000）
hermes --help             # 查看帮助
hermes --log-level DEBUG  # 指定日志级别
hermes --log-file logs/hermes.log  # 同时输出到文件
```

## Docker 部署

```bash
# 方式一：docker run
docker build -t hermes-workbench .
docker run -p 8000:8000 -e HERMES_API_TOKEN=your-secret hermes-workbench

# 方式二：docker compose（推荐，自动持久化状态）
docker compose up --build
```

Dashboard API 默认监听 8000 端口，`/health` 端点免认证。设置 `HERMES_API_TOKEN` 后，其余端点需 `Authorization: Bearer <token>` 认证。

## Workbench Dashboard

Workbench 提供完整的 HTTP Dashboard API 与单页前端（`prototype/index.html`），覆盖三阶段能力：

### Phase 1 · 统一管理
- **概览仪表盘**：providers、skills 就绪数、记忆层级概览
- **技能管理**：发现、搜索、运行（含依赖预检）
- **记忆管理**：L1 facts / L2 episodes / L3 profile 读写
- **任务管理**：注册、运行（含 recurring 模式）、取消
- **注册中心**：skills / agents / knowledge / user 统一视图
- **用户画像**：查看与编辑

### Phase 2 · 编排自动化
- **工作流引擎**：DAG 拓扑排序，支持步骤依赖与并行执行
- **触发器管理**：GitHub（PR/Issue）、Cron 定时、Webhook 三类触发器
- **执行监控**：实时查看工作流执行历史与步骤状态
- **SSE 实时推送**：`GET /events` 端点推送工作流执行进度，前端自动更新

### Phase 3 · 多项目调度
- **项目接入**：local / github / api 三类项目注册管理
- **跨项目同步**：技能、记忆、用户画像的资产同步
- **项目汇总**：连接状态、技能数、资产统计

### API 端点概览

| 类别 | 端点 | 说明 |
|------|------|------|
| 基础 | `GET /health` | 健康检查（免认证） |
| 技能 | `GET/POST /skills` | 列表 / 运行 |
| 记忆 | `GET/POST/PUT/DELETE /memory/*` | facts / episodes / profile |
| 任务 | `GET/POST /tasks` | 注册 / 运行 / 取消 |
| 搜索 | `GET /search?q=` | 全局搜索 skills / facts / tasks |
| 工作流 | `GET/POST/PUT/DELETE /workflows` | CRUD + 执行 + 历史 |
| 触发器 | `GET/POST/DELETE/PATCH /triggers` | CRUD + 启停 |
| 项目 | `GET/POST/DELETE /projects` | CRUD + 汇总 + 同步 |
| 实时 | `GET /events` | SSE 事件流 |


## 快速开始

```bash
cd /workspace/Hermes

# 1. 创建虚拟环境（已完成时可跳过）
python -m venv .venv
source .venv/bin/activate

# 2. 安装依赖与 hermes 命令（editable 模式）
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .

# 3. 复制环境变量模板并按需填写
#    留空的变量会自动尝试从主仓库 .env 继承
cp .env.example .env

# 4. 健康检查
hermes doctor

# 5. 启动
hermes
```

## 使用配置

```python
from hermes.config import get_settings
from hermes.skills import discover_skills, get_skill_path

settings = get_settings()
print(settings.openai_api_key)
print(settings.openclaw_model_primary)
print(settings.configured_providers())  # 列出已配置 Key 的提供商

for skill in discover_skills():
    print(skill.name, skill.path)
```

## 已沉淀的 Skills

Hermes 已从主仓库拉取 24 个 skills，包括：浏览器自动化、新闻摘要、搜索（Brave/Tavily）、抖音/微信/YouTube 内容读取、前端设计、GitHub/Notion/Obsidian/Trello 集成、Loop Engineering、产品经理、股票分析、Skill 创建/管理/审核、天气查询、自我改进 Agent 等。

## 开发

```bash
ruff check src/ tests/     # Lint
mypy src/                  # 类型检查
pytest tests/ -v           # 运行测试
```

### 同步更新主仓库 skills / 知识文档

```bash
rsync -av --delete /workspace/.trae/skills/ /workspace/Hermes/skills/
rsync -av --delete /workspace/.trae/docs/knowledge/ /workspace/Hermes/knowledge/
```

## 注意事项

- 永远不要把真实的 `.env` 文件提交到 git（已加入 `.gitignore`）。
- 如需更改主仓库路径，修改 `HERMES_MAIN_REPO_PATH` 环境变量。
- Hermes 是一个独立的 git 仓库，与 `/workspace` 主仓库分开管理。
- 各 skill 脚本可能依赖各自的运行时环境；运行前请阅读对应 skill 的 `SKILL.md`。
