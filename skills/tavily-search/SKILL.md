---
name: tavily
description: AI-optimized web search via Tavily API. Returns concise, relevant results for AI agents. 当用户需要搜索网络信息、查找最新资讯、研究某个主题、验证事实、获取网页内容时，使用此 skill。也适用于用户提到"搜索""查一下""找找""最新消息"等场景。
homepage: https://tavily.com
metadata: {"clawdbot":{"emoji":"🔍","requires":{"bins":["node"],"env":["TAVILY_API_KEY"]},"primaryEnv":"TAVILY_API_KEY"}}
---

# Tavily Search

AI 优化的网络搜索工具，专为 AI Agent 设计。返回干净、相关的内容，避免广告和噪音。

## 核心能力

| 功能 | 命令 | 适用场景 |
|------|------|---------|
| **搜索** | `search.mjs "query"` | 快速获取搜索结果 |
| **深度搜索** | `search.mjs "query" --deep` | 复杂研究问题，更全面 |
| **新闻搜索** | `search.mjs "query" --topic news` | 最新资讯、时事热点 |
| **内容提取** | `extract.mjs "URL"` | 从网页提取正文内容 |

## 标准工作流

### Step 1: 执行搜索

```bash
node {baseDir}/scripts/search.mjs "query" -n 5
```

**CHECKPOINT**: 是否获取到相关结果？
- 成功标志：返回 JSON 包含 `results` 数组，每项含 `title`、`url`、`content`
- 失败处理：如果返回空数组，尝试更换关键词或使用 `--deep` 深度搜索

### Step 2: 分析结果

从搜索结果中提取关键信息：
- `title` — 页面标题
- `url` — 原文链接
- `content` — 内容摘要
- `score` — 相关度分数（越高越相关）

**CHECKPOINT**: 结果是否足够回答用户问题？
- 如果摘要已足够，直接回答用户
- 如果需要全文，进入 Step 3

### Step 3: 提取全文（可选）

```bash
node {baseDir}/scripts/extract.mjs "https://example.com/article"
```

**CHECKPOINT**: 是否成功提取内容？
- 成功标志：返回 `content` 字段包含正文
- 失败处理：如果提取失败，尝试其他搜索结果链接

---

## 命令详解

### 搜索命令

```bash
# 基础搜索（返回 5 条结果）
node {baseDir}/scripts/search.mjs "人工智能最新进展"

# 指定结果数量（最多 20 条）
node {baseDir}/scripts/search.mjs "量子计算" -n 10

# 深度搜索（更全面，但较慢）
node {baseDir}/scripts/search.mjs "大模型微调最佳实践" --deep

# 新闻搜索（最新资讯）
node {baseDir}/scripts/search.mjs "AI 行业动态" --topic news

# 新闻搜索 + 时间限制（最近 7 天）
node {baseDir}/scripts/search.mjs "科技新闻" --topic news --days 7
```

### 内容提取命令

```bash
# 从 URL 提取正文
node {baseDir}/scripts/extract.mjs "https://example.com/article"

# 批量提取（多个 URL）
node {baseDir}/scripts/extract.mjs "url1" "url2" "url3"
```

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| API Key 未配置 | 环境变量缺失 | 提示用户设置 `TAVILY_API_KEY` |
| 搜索返回空 | 关键词太具体或太冷门 | 更换关键词，使用更通用的词 |
| 内容提取失败 | 网页需要登录或有反爬 | 尝试其他搜索结果链接 |
| 请求超时 | 网络问题或 API 限流 | 等待后重试，减少 `-n` 数量 |
| 结果不相关 | 关键词歧义 | 添加更多上下文词，使用 `--deep` |

### 失败时的用户通知

当搜索失败时，**明确告知用户**：

1. 具体失败原因
2. 已尝试的搜索词
3. 建议的替代方案

**示例**：
```
❌ 搜索"XYZ技术"未找到相关结果

已尝试：
- 关键词："XYZ技术"
- 搜索类型：普通搜索

建议：
- 尝试更通用的关键词，如"XYZ"或"XYZ应用"
- 使用 `--deep` 深度搜索
- 如果是新术语，可能尚未被广泛报道

是否需要我尝试其他关键词？
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 搜索敏感个人信息 | 隐私风险 | 仅搜索公开信息 |
| ❌ 无限制调用 API | 成本失控 | 设置 `-n` 限制结果数 |
| ❌ 忽略 API 限流 | 可能被封禁 | 遇到 429 错误时等待重试 |
| ❌ 不验证 API Key | 必然失败 | 先检查环境变量 |
| ❌ 搜索过于宽泛的词 | 结果噪音大 | 添加限定词缩小范围 |

### 错误示例（反例）

**❌ 错误示例 1：搜索词过于宽泛**

```bash
node {baseDir}/scripts/search.mjs "AI"
```

**问题**：返回结果太多且不相关，无法有效使用

**✅ 正确做法**：

```bash
node {baseDir}/scripts/search.mjs "AI 大模型微调技术 2024" -n 5
```

---

**❌ 错误示例 2：不检查 API Key**

```bash
node {baseDir}/scripts/search.mjs "query"  # 直接报错
```

**问题**：API Key 未配置时会直接失败

**✅ 正确做法**：

```bash
# 先检查环境变量
echo $TAVILY_API_KEY
# 如果为空，提示用户配置
```

---

**❌ 错误示例 3：忽略搜索结果的分数**

```bash
# 直接使用第一个结果
node {baseDir}/scripts/extract.mjs "<第一个结果的URL>"
```

**问题**：第一个结果可能相关度不高

**✅ 正确做法**：

```bash
# 优先选择 score > 0.8 的结果
# 如果没有高分结果，使用 --deep 深度搜索
```

---

## FAQ 常见问题

**Q: Tavily 和普通搜索引擎有什么区别？**
A: Tavily 专为 AI Agent 优化，返回干净的内容摘要而非完整网页，减少噪音和 token 消耗。

**Q: 什么时候用 `--deep` 深度搜索？**
A: 复杂研究问题、学术查询、需要更全面信息时使用。注意深度搜索较慢，建议普通搜索无果时再用。

**Q: 什么时候用 `--topic news`？**
A: 查找最新资讯、时事热点、行业动态时使用。可配合 `--days` 限制时间范围。

**Q: 搜索结果中的 score 是什么？**
A: 相关度分数，范围 0-1，越高表示与查询越相关。建议优先使用 score > 0.8 的结果。

**Q: 如何获取网页全文而非摘要？**
A: 先用 `search.mjs` 找到相关链接，再用 `extract.mjs` 提取全文。

**Q: API Key 如何获取？**
A: 访问 https://tavily.com 注册账号，在 Dashboard 获取 API Key，设置环境变量 `TAVILY_API_KEY`。

**Q: 搜索结果数量有限制吗？**
A: 每次最多 20 条（`-n 20`）。建议从 5 条开始，不够再增加。

**Q: 如何处理搜索结果为空？**
A: 1) 更换关键词 2) 使用更通用的词 3) 尝试 `--deep` 深度搜索 4) 确认该信息确实存在于网络上。

---

## 环境配置

### 必需环境变量

```bash
export TAVILY_API_KEY="tvly-xxxxxxxxxxxxx"
```

### 获取 API Key

1. 访问 https://tavily.com
2. 注册账号（支持 Google/GitHub 登录）
3. 进入 Dashboard → API Keys
4. 复制 API Key 并设置环境变量

### 验证配置

```bash
# 检查环境变量
echo $TAVILY_API_KEY

# 测试搜索
node {baseDir}/scripts/search.mjs "test" -n 1
```
