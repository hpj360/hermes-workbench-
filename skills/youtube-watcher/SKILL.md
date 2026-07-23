---
name: youtube-watcher
description: Fetch and read transcripts from YouTube videos. Use when you need to summarize a video, answer questions about its content, or extract information from it. 也适用于用户提到"油管视频""YouTube""看视频""视频字幕""这个视频说了什么"。
author: michael gathara
version: 1.0.0
triggers:
  - "watch youtube"
  - "summarize video"
  - "video transcript"
  - "youtube summary"
  - "analyze video"
metadata: {"clawdbot":{"emoji":"📺","requires":{"bins":["yt-dlp"]},"install":[{"id":"brew","kind":"brew","formula":"yt-dlp","bins":["yt-dlp"],"label":"Install yt-dlp (brew)"},{"id":"pip","kind":"pip","package":"yt-dlp","bins":["yt-dlp"],"label":"Install yt-dlp (pip)"}]}}
---

# YouTube Watcher

从 YouTube 视频提取字幕文字，支持总结、问答、内容提取。

## 标准工作流

### Step 1: 验证依赖

**CHECKPOINT**: `yt-dlp` 是否可用？
- 验证：`which yt-dlp` 或 `yt-dlp --version`
- 可用：继续
- 不可用：提示用户安装（`pip install yt-dlp` 或 `brew install yt-dlp`）

### Step 2: 提取字幕

```bash
python3 {baseDir}/scripts/get_transcript.py "<YouTube URL>"
```

支持的 URL 格式：
- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://www.youtube.com/embed/VIDEO_ID`

**CHECKPOINT**: 是否获取到字幕？
- 成功：字幕文本被输出
- 失败（无字幕）：告知用户并提供替代方案
- 失败（其他错误）：进入失败处理流程

### Step 3: 处理字幕内容

根据用户需求选择处理方式：

| 需求 | 处理方式 |
|------|---------|
| 总结视频 | 提取核心观点，生成结构化摘要 |
| 回答问题 | 在字幕中搜索相关段落，直接引用 |
| 提取信息 | 提取关键数据、时间点、步骤 |
| 翻译内容 | 保留原文+翻译的双语字幕 |

**CHECKPOINT**: 字幕是否太长需要分段？
- 超过 10000 字：分段处理，每段独立总结后合并
- 有明确章节：按章节分段处理

---

## 已知限制

| 限制 | 说明 | 应对方案 |
|------|------|---------|
| 无字幕视频 | 视频关闭了字幕且无自动生成字幕 | 告知用户"此视频无字幕，无法提取" |
| 自动生成字幕质量 | 可能有识别错误 | 标注"字幕为自动生成，可能有误差" |
| 非英语字幕 | 非英语视频可能有翻译不准确 | 标注原文语言，谨慎翻译 |
| 受限视频 | 年龄限制/地区限制视频 | 告知用户地区限制，无法访问 |

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| yt-dlp 未安装 | 未安装或 PATH 不正确 | 提示用户安装（pip/brew） |
| 无字幕可用 | 视频无字幕且未开启自动字幕 | 告知用户"此视频无法提取字幕" |
| 视频被删除/不可用 | 视频已下架或设为私有 | 告知用户"视频不可用" |
| 网络请求超时 | 网络问题 | 增加超时参数重试 |
| URL 格式不正确 | 用户提供的链接格式有问题 | 尝试从用户输入中提取有效 URL |
| 字幕语言不匹配 | 需要特定语言但默认获取了其他语言 | 指定语言参数重试 |

### 失败时的用户通知

```
❌ 无法获取视频字幕

原因：
- 此视频无字幕可用
- 或视频存在地区限制

替代方案：
1. 请在 YouTube 页面手动复制字幕（点击 ... → 打开字幕 → 复制）
2. 将字幕文本直接粘贴给我
3. 我来帮你总结和分析
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 对无字幕视频假装成功 | 返回空内容浪费用户时间 | 明确告知无字幕，提供替代方案 |
| ❌ 不检查 URL 有效性 | 浪费调用 | 先验证 URL 格式是否正确 |
| ❌ 直接输出超长字幕 | 用户无法阅读 | 分段处理，生成摘要 |
| ❌ 忽略自动字幕质量 | 用户可能误解内容 | 标注字幕来源（自动生成/用户上传） |
| ❌ 尝试绕过地区限制 | 可能违反服务条款 | 告知用户地区限制，建议其他视频源 |

### 错误示例（反例）

**❌ 错误示例 1：不检查字幕可用性**

```
执行：python3 get_transcript.py "https://youtube.com/watch?v=xxx"
结果：报错"no subtitles available"
用户困惑：我不知道发生了什么
```

**✅ 正确做法**：

```
执行：python3 get_transcript.py "URL"

如果无字幕：
❌ 此视频无字幕可用（既无手动字幕，也无自动字幕）

建议：
1. 请在 YouTube 页面手动复制字幕给我
2. 或提供视频的文字描述/摘要
3. 此视频时长较短，您可以直接观看原视频
```

---

**❌ 错误示例 2：直接输出超长字幕**

```
获取到 30 分钟视频字幕（15000 字）
直接输出全部字幕给用户
用户：这么多字怎么读？
```

**✅ 正确做法**：

```
1. 评估字幕长度（>10000字需分段）
2. 生成结构化摘要：
   - 视频主题
   - 核心要点（3-5 条）
   - 关键时间点
   - 结论和行动建议
3. 如果用户需要，再提供完整字幕供查阅
```

---

## FAQ 常见问题

**Q: 为什么有些视频没有字幕？**
A: 创作者可能关闭了字幕功能、该视频没有自动生成字幕、或视频太新自动字幕尚未生成。

**Q: 自动字幕质量如何？**
A: 英语质量较高，中文和其他语言可能有一定误差。对于重要内容，建议对照原视频核实。

**Q: 能获取实时字幕（YouTube Live）吗？**
A: 不支持。YouTube Live 的字幕是实时生成的，结束后不会保留。

**Q: 如何指定字幕语言？**
A: yt-dlp 支持 `--write-subs --sub-langs "zh-Hans"` 指定语言字幕。

**Q: 能获取翻译后的字幕吗？**
A: yt-dlp 可以下载多语言字幕，但翻译需要通过其他工具（如 YouTube Translate 功能）。

**Q: 视频太长字幕太多怎么办？**
A: 分段处理：每 5000-10000 字为一段，各段独立总结后合并为完整摘要。
