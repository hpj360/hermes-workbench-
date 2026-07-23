---
name: summarize
description: Summarize URLs or files with the summarize CLI (web, PDFs, images, audio, YouTube).
homepage: https://summarize.sh
metadata: {"clawdbot":{"emoji":"🧾","requires":{"bins":["summarize"]},"install":[{"id":"brew","kind":"brew","formula":"steipete/tap/summarize","bins":["summarize"],"label":"Install summarize (brew)"}]}}
---

# Summarize

Fast CLI to summarize URLs, local files, and YouTube links.

## Quick start

```bash
summarize "https://example.com" --model google/gemini-3-flash-preview
summarize "/path/to/file.pdf" --model google/gemini-3-flash-preview
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto
```

## Model + keys

Set the API key for your chosen provider:
- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- xAI: `XAI_API_KEY`
- Google: `GEMINI_API_KEY` (aliases: `GOOGLE_GENERATIVE_AI_API_KEY`, `GOOGLE_API_KEY`)

Default model is `google/gemini-3-flash-preview` if none is set.

## Useful flags

- `--length short|medium|long|xl|xxl|<chars>`
- `--max-output-tokens <count>`
- `--extract-only` (URLs only)
- `--json` (machine readable)
- `--firecrawl auto|off|always` (fallback extraction)
- `--youtube auto` (Apify fallback if `APIFY_API_TOKEN` set)

## Config

Optional config file: `~/.summarize/config.json`

```json
{ "model": "openai/gpt-5.2" }
```

Optional services:
- `FIRECRAWL_API_KEY` for blocked sites
- `APIFY_API_TOKEN` for YouTube fallback

---

## 标准工作流

### Step 1: 检测 summarize CLI 可用性

**CHECKPOINT**: `summarize` 命令是否可用？
- 验证：运行 `which summarize` 或 `summarize --version`
- 可用：继续
- 不可用：提示用户安装（`brew install steipete/tap/summarize`）或使用备选方案（直接读取网页/文件内容，由 Claude 总结）

### Step 2: 确定输入类型

根据用户输入判断类型：
- **URL**（含 `http://` 或 `https://`）：使用 `summarize "URL"`
- **YouTube 链接**（含 `youtube.com` 或 `youtu.be`）：使用 `summarize "URL" --youtube auto`
- **本地文件路径**（如 `.pdf` `.txt` `.md` `.doc` `.docx`）：使用 `summarize "/path/to/file"`
- **图片**（`.png` `.jpg` `.webp`）：使用 `summarize "/path/to/image.png"`
- **音频**（`.mp3` `.wav` `.m4a`）：使用 `summarize "/path/to/audio.mp3"`

**CHECKPOINT**: 输入类型是否可识别？
- 可识别：进入对应分支
- 不可识别：询问用户澄清，或尝试直接调用 summarize 让 CLI 自动检测

### Step 3: 选择参数

根据用户需求设置参数：
- 摘要长度：`--length short|medium|long|xl|xxl|500`
- 结构化输出：`--json`
- 仅提取：`--extract-only`（URL）
- 模型选择：`--model openai/gpt-5.2`（默认 `google/gemini-3-flash-preview`）
- YouTube: `--youtube auto`

**CHECKPOINT**: API key 是否配置？
- 检查：`echo $OPENAI_API_KEY` 或 `echo $GEMINI_API_KEY` 或 `echo $ANTHROPIC_API_KEY`
- 已配置：继续
- 未配置：提示用户设置 API key，或使用备选方案（直接读取 + Claude 总结）

### Step 4: 执行并输出

```bash
summarize "<input>" --model google/gemini-3-flash-preview [其他参数]
```

**CHECKPOINT**: 是否获得有效摘要？
- 成功：向用户展示结构化摘要
- 失败（API 错误、超时、空响应）：进入失败处理流程

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| summarize 命令不存在 | 未安装或 PATH 不正确 | 提示用户安装（brew），或使用备选方案（直接读取 + Claude 总结） |
| API key 未配置 | 环境变量缺失 | 提示用户设置 `OPENAI_API_KEY` 或 `GEMINI_API_KEY` |
| API 调用失败 | 网络问题、API 限流、额度不足 | 等待重试；更换模型；提示用户检查 API 状态 |
| PDF 读取失败 | PDF 加密或格式特殊 | 提取文本内容，由 Claude 直接总结 |
| YouTube 提取失败 | 需要 APIFY token 或视频被限制 | 提示用户提供文字内容或截图 |
| 图片/音频不支持 | 文件格式或大小问题 | 转换格式后重试；或直接提供内容给 Claude |
| 超长内容被截断 | 文件过大或内容过长 | 使用 `--length long` 或 `--xxl`；分批处理 |

### 失败时的用户通知

当 summarize 失败时，**明确告知用户**并提供替代方案：

```
⚠️  summarize 命令调用失败

原因：
- API key 未配置（GEMINI_API_KEY 未设置）

建议：
1. 设置 API key: export GEMINI_API_KEY="your-key"
2. 或直接给我内容，我来帮你总结
3. 或我直接读取网页内容并总结（适用于 URL）

要我帮你用方案 3（直接读取 + 总结）吗？
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 在 summary 中直接输出 API key | 安全风险 | 从不展示或记录 API key |
| ❌ 用 summarize 处理敏感信息 | 数据通过第三方 API 传输 | 对于敏感文档，建议用户直接提供内容（不走 summarize） |
| ❌ 忽略 API 错误直接静默 | 用户不知道失败原因 | 明确展示错误信息和建议 |
| ❌ 对超长 PDF 不截断 | 可能超时或费用过高 | 先用 `--length short` 测试；必要时分段处理 |
| ❌ 不检查文件路径有效性 | 浪费调用额度 | 先 `ls <path>` 确认文件存在 |
| ❌ 默认使用最昂贵模型 | 不必要的高成本 | 默认使用 `google/gemini-3-flash-preview`（快速且低成本） |

### 错误示例（反例）

**❌ 错误示例 1：不验证直接调用**

```
用户：总结这个 PDF：~/Documents/report.pdf
执行：summarize ~/Documents/report.pdf
结果：文件不存在（路径中 ~ 未展开）
```

**✅ 正确做法**：

```
1. ls ~/Documents/report.pdf 确认文件存在
2. 展开绝对路径：summarize "$HOME/Documents/report.pdf"
3. 使用 --length short 先获得快速摘要，根据用户需要再扩展
```

---

**❌ 错误示例 2：不询问直接用最长摘要**

```
执行：summarize "URL" --length xxl
结果：生成 5000 字总结，用户只需要要点
```

**✅ 正确做法**：

```
1. 默认 medium 长度
2. 根据用户需求（"简要"、"详细"）调整 --length
3. 先获得短摘要，询问用户是否需要更多细节
```

---

**❌ 错误示例 3：不检查 API key**

```
执行：summarize "URL"
结果：报错 "API key not configured"，用户困惑
```

**✅ 正确做法**：

```
1. 执行前检查 echo $OPENAI_API_KEY 或 $GEMINI_API_KEY
2. 如果为空，告知用户如何配置
3. 配置后再执行
```

---

## FAQ 常见问题

**Q: summarize 和让 Claude 直接总结有什么区别？**
A: summarize CLI 内置了文件解析（PDF、图片、音频、视频字幕）和内容提取（Firecrawl、Apify），对复杂格式比单纯读取文件效果更好。Claude 适合对已提取文本的二次总结和分析。

**Q: 支持哪些文件格式？**
A: URL（网页）、PDF、TXT、Markdown、DOC/DOCX、图片（PNG/JPG/WEBP）、音频（MP3/WAV/M4A）、YouTube 链接。

**Q: 如何处理受保护的网页？**
A: 设置 `FIRECRAWL_API_KEY`，使用 `--firecrawl auto` 参数自动回退到 Firecrawl 抓取。

**Q: 如何处理 YouTube 视频？**
A: `summarize "https://youtu.be/..." --youtube auto`。配合 `APIFY_API_TOKEN` 可以处理受限视频。

**Q: 如何获得结构化的 JSON 输出？**
A: 添加 `--json` 参数：`summarize "URL" --json`。

**Q: 如何选择合适的模型？**
A: 默认 `google/gemini-3-flash-preview`（快速、低成本）。需要更高质量时用 `--model openai/gpt-5.2` 或 `--model anthropic/claude-sonnet-4.2`。

**Q: summarize 生成的摘要太长怎么办？**
A: 使用 `--length short` 参数，或让 Claude 对结果进行二次精简。

**Q: 如何避免 API 额度用尽？**
A: 监控 API 提供商的用量 dashboard；默认使用低成本模型；批量处理时使用 `--length short`。

**Q: 可以批量处理多个文件吗？**
A: 可以逐个调用 summarize，让用户决定先处理哪一个。对于多个 URL，建议逐个执行并及时展示结果。

**Q: 输出结果中出现乱码或格式问题怎么办？**
A: 这通常是源文件的编码问题。可以让 summarize 以 `--json` 输出后再格式化，或提取文本让 Claude 直接处理。
