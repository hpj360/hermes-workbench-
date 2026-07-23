---
name: figma-reader
description: |
  Figma REST API 封装。读取 Figma 文件、节点、组件、图片，导出为 JSON/PNG/SVG
  给 design-system/storybook 等下游 skill 使用。
  Use when: 从 Figma URL/file-key 提取设计资产；批量导出组件；对比本地 token 与
  Figma 源；为 Chromatic 视觉回归准备 baseline 图。
  Not for: 编辑 Figma 文件（只读）；Figma Plugin 开发（用 plugin API 而非 REST）。
---

# Figma Reader

> **核心思想**：把 Figma REST API 的 4 个核心端点封装为 Python CLI，让 AI Agent
> 能在不打开 Figma 客户端的情况下拉取设计资产。

---

## 1. 目录结构

```
figma-reader/
├── SKILL.md                  # 本文件
├── _meta.json
├── references/
│   ├── api-reference.md      # Figma REST API 端点速查
│   └── url-parsing.md        # Figma URL → file-key + node-id
├── scripts/
│   ├── client.py             # Figma REST API 客户端（requests）
│   ├── read_file.py          # 读完整文件
│   ├── read_nodes.py         # 读指定节点
│   ├── export_images.py      # 导出 PNG/SVG
│   ├── export_components.py  # 导出组件元数据
│   └── parse_url.py          # Figma URL 解析
└── data/
    └── sample_response.json  # 示例响应（用于 mock 测试）
```

## 2. 快速开始

### 2.1 配置 token

```bash
export FIGMA_TOKEN="figd_xxxxxxxxxxxxxxxx"
```

获取 token：Figma → Account Settings → Personal Access Tokens

### 2.2 读文件

```bash
python3 scripts/read_file.py --file-key ABC123 --output file.json
```

### 2.3 读节点

```bash
python3 scripts/read_nodes.py --file-key ABC123 --node-ids "1:2,3:4" --output nodes.json
```

### 2.4 导出图片

```bash
python3 scripts/export_images.py \
  --file-key ABC123 \
  --node-ids "1:2,3:4" \
  --format png \
  --scale 2 \
  --output-dir ./images
```

### 2.5 解析 URL

```bash
python3 scripts/parse_url.py "https://www.figma.com/file/ABC123/My-File?node-id=1%3A2"
# 输出: file_key=ABC123 node_id=1:2
```

## 3. URL 解析规则

| URL 形式 | file_key | node_id |
|----------|----------|---------|
| `/file/{key}/...` | {key} | 来自 `?node-id=` |
| `/design/{key}/...` | {key} | 来自 `?node-id=` |
| `/proto/{key}/...` | {key} | 来自 `?node-id=` |
| `figma.com/file/{key}?node-id=1-2` | {key} | `1:2`（`-` → `:`） |

## 4. 限流

- X-Figma-Token 限制：**每分钟 60 次请求**
- 批量读取时用 `--batch-size 20` 分批
- 遇到 429 响应时退避 60 秒

## 5. 设计原则

- **从约束出发**：Figma REST 限制就是约束（60 req/min、payload 5MB）
- **只读不写**：本 skill 不修改 Figma 文件
- **下游友好**：输出统一 JSON Schema，方便 storybook-chromatic / ui-design-system 消费
