---
name: notion
description: Notion API for creating and managing pages, databases, and blocks.
homepage: https://developers.notion.com
metadata: {"clawdbot":{"emoji":"📝"}}
---

# notion

Use the Notion API to create/read/update pages, data sources (databases), and blocks.

## Setup

1. Create an integration at https://notion.so/my-integrations
2. Copy the API key (starts with `ntn_` or `secret_`)
3. Store it:
```bash
mkdir -p ~/.config/notion
echo "ntn_your_key_here" > ~/.config/notion/api_key
```
4. Share target pages/databases with your integration (click "..." → "Connect to" → your integration name)

## API Basics

All requests need:
```bash
NOTION_KEY=$(cat ~/.config/notion/api_key)
curl -X GET "https://api.notion.com/v1/..." \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json"
```

> **Note:** The `Notion-Version` header is required. This skill uses `2025-09-03` (latest). In this version, databases are called "data sources" in the API.

## Common Operations

**Search for pages and data sources:**
```bash
curl -X POST "https://api.notion.com/v1/search" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"query": "page title"}'
```

**Get page:**
```bash
curl "https://api.notion.com/v1/pages/{page_id}" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03"
```

**Get page content (blocks):**
```bash
curl "https://api.notion.com/v1/blocks/{page_id}/children" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03"
```

**Create page in a data source:**
```bash
curl -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"database_id": "xxx"},
    "properties": {
      "Name": {"title": [{"text": {"content": "New Item"}}]},
      "Status": {"select": {"name": "Todo"}}
    }
  }'
```

**Query a data source (database):**
```bash
curl -X POST "https://api.notion.com/v1/data_sources/{data_source_id}/query" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {"property": "Status", "select": {"equals": "Active"}},
    "sorts": [{"property": "Date", "direction": "descending"}]
  }'
```

**Create a data source (database):**
```bash
curl -X POST "https://api.notion.com/v1/data_sources" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"page_id": "xxx"},
    "title": [{"text": {"content": "My Database"}}],
    "properties": {
      "Name": {"title": {}},
      "Status": {"select": {"options": [{"name": "Todo"}, {"name": "Done"}]}},
      "Date": {"date": {}}
    }
  }'
```

**Update page properties:**
```bash
curl -X PATCH "https://api.notion.com/v1/pages/{page_id}" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{"properties": {"Status": {"select": {"name": "Done"}}}}'
```

**Add blocks to page:**
```bash
curl -X PATCH "https://api.notion.com/v1/blocks/{page_id}/children" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "children": [
      {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": "Hello"}}]}}
    ]
  }'
```

## Property Types

Common property formats for database items:
- **Title:** `{"title": [{"text": {"content": "..."}}]}`
- **Rich text:** `{"rich_text": [{"text": {"content": "..."}}]}`
- **Select:** `{"select": {"name": "Option"}}`
- **Multi-select:** `{"multi_select": [{"name": "A"}, {"name": "B"}]}`
- **Date:** `{"date": {"start": "2024-01-15", "end": "2024-01-16"}}`
- **Checkbox:** `{"checkbox": true}`
- **Number:** `{"number": 42}`
- **URL:** `{"url": "https://..."}`
- **Email:** `{"email": "a@b.com"}`
- **Relation:** `{"relation": [{"id": "page_id"}]}`

## Key Differences in 2025-09-03

- **Databases → Data Sources:** Use `/data_sources/` endpoints for queries and retrieval
- **Two IDs:** Each database now has both a `database_id` and a `data_source_id`
  - Use `database_id` when creating pages (`parent: {"database_id": "..."}`)
  - Use `data_source_id` when querying (`POST /v1/data_sources/{id}/query`)
- **Search results:** Databases return as `"object": "data_source"` with their `data_source_id`
- **Parent in responses:** Pages show `parent.data_source_id` alongside `parent.database_id`
- **Finding the data_source_id:** Search for the database, or call `GET /v1/data_sources/{data_source_id}`

## Notes

- Page/database IDs are UUIDs (with or without dashes)
- The API cannot set database view filters — that's UI-only
- Rate limit: ~3 requests/second average
- Use `is_inline: true` when creating data sources to embed them in pages

---

## 标准工作流

### Step 1: 验证 API Key

**CHECKPOINT**: `NOTION_KEY` 是否配置？
- 验证：`cat ~/.config/notion/api_key`
- 已配置：继续
- 未配置：提示用户配置（见 Setup 部分）

**CHECKPOINT**: API Key 是否有效？
- 测试：`curl "https://api.notion.com/v1/users/me" -H "Authorization: Bearer $NOTION_KEY"`
- 返回用户信息：Key 有效
- 返回错误：Key 无效，重新配置

### Step 2: 理解用户需求

| 需求类型 | 对应操作 |
|---------|---------|
| 搜索页面 | `POST /v1/search` |
| 读取页面内容 | `GET /v1/pages/{page_id}` |
| 读取块内容 | `GET /v1/blocks/{page_id}/children` |
| 创建页面 | `POST /v1/pages` |
| 查询数据库 | `POST /v1/data_sources/{id}/query` |
| 创建数据库 | `POST /v1/data_sources` |
| 更新页面属性 | `PATCH /v1/pages/{page_id}` |
| 添加块 | `PATCH /v1/blocks/{page_id}/children` |

### Step 3: 执行操作

**CHECKPOINT**: 目标页面/数据库是否已分享给 Integration？
- Notion API 只能访问被明确分享的页面/数据库
- 如果返回 404 或权限错误，检查 Integration 设置

### Step 4: 验证结果

**CHECKPOINT**: API 返回状态码是否为 200？
- 成功：向用户展示结构化结果
- 失败：进入失败处理流程

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| API Key 未配置 | 环境变量缺失 | 提示用户配置 `~/.config/notion/api_key` |
| API Key 无效 | Key 过期或错误 | 提示用户重新获取 API Key |
| 权限错误 404 | 页面/数据库未分享给 Integration | 告知用户在 Notion 中手动分享（点击 ... → Connect → integration name） |
| 速率限制 429 | 每秒超过 ~3 次请求 | 等待 1 秒后重试；添加请求间隔 |
| API 版本过时 | Notion-Version 不正确 | 确认为 `2022-06-28` 或更新版本 |
| Block ID 格式错误 | ID 不是有效 UUID | 检查 ID 格式（32 位十六进制，可带连字符） |
| 数据库结构不匹配 | 创建页面时属性不存在 | 先查询数据库结构，确保属性名称匹配 |
| 数据库/数据源混淆 | 2025-09-03 API 改了 | 创建页面用 `database_id`，查询用 `data_source_id` |

### 失败时的用户通知

```
❌ 无法访问 Notion 页面

原因：
- API Key 未配置或无效
- 或页面未分享给此 Integration

建议：
1. 检查 API Key：cat ~/.config/notion/api_key
2. 在 Notion 中打开目标页面，点击 ... → Connect → 您的 Integration 名称
3. 重新尝试操作
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 不检查页面分享状态 | 必然收到 404 错误 | 操作前确认页面已分享给 Integration |
| ❌ 不处理速率限制 | 收到 429 错误 | 添加请求间隔（每秒最多 3 次） |
| ❌ 混用 database_id 和 data_source_id | API 端点不匹配 | 创建页面用 database_id，查询用 data_source_id |
| ❌ 硬编码 API Key | 安全风险 | 使用配置文件或环境变量 |
| ❌ 不验证 Block 类型 | 导致块创建失败 | 创建前确认块类型的 JSON 格式正确 |
| ❌ 忽略 API 版本 | 使用过时的 API 端点 | 确认 Notion-Version 为最新版本 |

### 错误示例（反例）

**❌ 错误示例 1：不检查页面分享状态**

```
执行：GET /v1/pages/xxx
结果：{"object":"error", "status":404, "code":"object_not_found"}
用户困惑：为什么找不到页面？
```

**✅ 正确做法**：

```
执行 GET /v1/pages/xxx 前：
1. 确认 API Key 有效
2. 确认目标页面已分享给 Integration
3. 如果是新建 Integration，需要重新分享页面
```

---

**❌ 错误示例 2：混淆 database_id 和 data_source_id**

```
# 查询数据库错误地使用 database_id
POST /v1/data_sources/{database_id}/query
结果：404 或数据为空
```

**✅ 正确做法**：

```
# 创建页面 → 使用 database_id
POST /v1/pages
{"parent": {"database_id": "xxx"}, ...}

# 查询数据库 → 使用 data_source_id
POST /v1/data_sources/{data_source_id}/query
```

---

## FAQ 常见问题

**Q: database_id 和 data_source_id 有什么区别？**
A: 2025-09-03 版本后，每个数据库有两个 ID：创建页面时用 `database_id`，查询和检索时用 `data_source_id`。两者不同但关联同一数据库。

**Q: 如何获取页面或数据库的 ID？**
A: 在 Notion 页面 URL 中提取（`notion.so/workspace/页面名称-32位ID`）。搜索 API也可以找到。

**Q: 速率限制是多少？**
A: 平均每秒 3 次请求。超过会收到 429 错误。建议在脚本中添加延迟控制。

**Q: 如何更新数据库的结构（添加属性）？**
A: 使用 `PATCH /v1/data_sources/{id}` 更新数据库属性定义。

**Q: 可以直接在页面中创建数据库吗？**
A: 可以，使用 `is_inline: true` 参数创建嵌入式数据库。

**Q: Block 的类型有哪些？**
A: 常用：paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item, image, code, quote, callout, divider, to_do, toggle, table。

**Q: 如何获取 Block 的完整嵌套内容？**
A: 需要递归调用 `/blocks/{id}/children`，因为 Notion 只返回一层子块。

**Q: Notion API 可以设置视图过滤（filter）吗？**
A: 不能，设置视图过滤是 Notion UI 功能，API 不支持。

**Q: 如何处理中文内容？**
A: Notion API 完全支持中文。只需要确保 JSON 中的中文是有效的 UTF-8 编码。
