---
name: douyin-reader
description: 完整提取抖音视频内容（语音+画面+内嵌文字）。当用户提供抖音视频链接（douyin.com、v.douyin.com）并要求阅读、学习、总结、提取文字、获取字幕、转录内容、分析画面、OCR 识别时，必须使用此 skill。也适用于"抖音视频""抖音链接""这个视频""看看这个抖音"等场景。8 项能力覆盖视频内容全部维度：SSR 解析、无水印下载、语音转写+时间轴、长视频分段转写、画面抽帧、OCR 内嵌文字、LLM 校对、评论区提取。
---

# 抖音视频内容提取器（完整能力版）

视频内容 = 语音 + 画面 + 内嵌文字 + 互动。本 skill 覆盖全部维度，8 项能力完整提取视频内容。

## 能力矩阵

| # | 能力 | 实现 | 依赖 | 状态 |
|---|------|------|------|------|
| 1 | 链接解析 | iesdouyin SSR | requests | ✅ 实测可用 |
| 2 | 元数据 | _ROUTER_DATA JSON | - | ✅ |
| 3 | 无水印下载 | playwm→play | requests | ✅ |
| 4 | 语音转写+时间轴 | openai-whisper | openai-whisper, ffmpeg | ✅ |
| 5 | 长视频完整转写 | 分段转写+时间轴偏移拼接 | openai-whisper, ffmpeg | ✅ |
| 6 | 画面抽帧 | ffmpeg 按间隔抽帧 | ffmpeg | ✅ |
| 7 | 内嵌文字 OCR | rapidocr-onnxruntime | rapidocr-onnxruntime | ✅ |
| 8 | LLM 校对 | 提示词模板，调用方执行 | - | ✅ |
| 9 | 评论区提取 | agent-browser | agent-browser | 降级方案 |

## 依赖安装

```bash
pip install requests openai-whisper rapidocr-onnxruntime
# ffmpeg 系统安装：apt install ffmpeg / brew install ffmpeg
```

## 降级策略

```
Layer 1: douyin_reader.py SSR 解析（首选，无需 Cookie/Key）
    ↓ 失败
Layer 2: agent-browser 提取页面信息 + 评论区（降级，只能拿文字）
    ↓ 失败
Layer 3: WebSearch 搜索视频相关信息（最后手段）
```

## Layer 1: douyin_reader.py（首选，8 项能力）

**实测结论（2026-07-11）：** 通过 iesdouyin.com 分享页的 SSR 数据直接解析无水印视频直链，无需 Cookie、无需 API Key、无需浏览器。实测完整跑通解析→下载→转写→抽帧→OCR 全链路。

### 基础用法

```bash
# 默认：解析+下载+转写(前5分钟) + 时间轴 segments
python3 /workspace/skills/douyin-reader/scripts/douyin_reader.py "<URL>" --json

# 快速预览（低质量转写）
python3 /workspace/skills/douyin-reader/scripts/douyin_reader.py "<URL>" --model tiny --max-duration 120 --json

# 只解析+下载，不转写
python3 /workspace/skills/douyin-reader/scripts/douyin_reader.py "<URL>" --skip-transcribe --json
```

### 完整能力用法

```bash
# 长视频完整转写（分段拼接，118分钟≈24段×5分钟）
python3 /workspace/skills/douyin-reader/scripts/douyin_reader.py "<URL>" --full-transcribe --json

# 抽帧 + OCR（提取画面内嵌文字，如 PPT/代码块/字幕）
python3 /workspace/skills/douyin-reader/scripts/douyin_reader.py "<URL>" --extract-frames --ocr --skip-transcribe --json

# 全能力：转写 + 抽帧 + OCR + LLM 校对提示词
python3 /workspace/skills/douyin-reader/scripts/douyin_reader.py "<URL>" \
  --full-transcribe --extract-frames --ocr --llm-correct-prompt --json
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--model` | small | Whisper 模型（tiny/base/small/medium/large） |
| `--language` | zh | 音频语言 |
| `--max-duration` | 300 | 转写最大时长（秒），与 --full-transcribe 互斥 |
| `--full-transcribe` | off | 完整转写（分段拼接，长视频用） |
| `--segment-duration` | 300 | 完整转写时分段长度（秒） |
| `--extract-frames` | off | 抽帧（供 VLM 画面理解） |
| `--frame-interval` | 30 | 抽帧间隔（秒） |
| `--ocr` | off | 对帧做 OCR（需 --extract-frames） |
| `--skip-transcribe` | off | 跳过语音转写 |
| `--llm-correct-prompt` | off | 输出 LLM 校对提示词 |
| `--json` | off | JSON 格式输出 |

### 输出字段（JSON）

```json
{
  "success": true,
  "video_id": "xxx",
  "title": "标题",
  "author": "作者",
  "duration": 7120.5,
  "like_count": 330,
  "comment_count": 75,
  "share_count": 82,
  "transcription": {
    "full_text": "完整转写文字",
    "segments": [
      {"start": 0.0, "end": 3.5, "text": "第一句"},
      {"start": 3.5, "end": 7.2, "text": "第二句"}
    ],
    "language": "zh",
    "model": "small",
    "total_segments": 24
  },
  "frames": ["/tmp/douyin_xxx/frames/frame_00001.jpg", "..."],
  "ocr_results": [
    {"frame": "...", "frame_num": 1, "timestamp": 30.0, "texts": ["GStack 部署", "七步冲刺工作流"]}
  ],
  "llm_correct_prompt": "请校对以下抖音视频转写文字..."
}
```

### Whisper 模型选择（实测对比，2026-07-11 沙箱 CPU）

| 模型 | 大小 | 速度 | 质量 | 备注 |
|------|------|------|------|------|
| tiny | 72MB | 3分钟音频/10.5s | 差，简繁混杂，错字多 | 快速预览 |
| small | 461MB | 1分钟音频/21.9s | 良，语义清晰，专有名词需校对 | **默认推荐** |
| medium | 1.5GB | - | - | OOM Killed，沙箱不可用 |

### 长视频分段转写原理

118 分钟视频在 CPU 上无法一次性转写（内存不足）。方案：
1. 按 `--segment-duration`（默认 300 秒）把音频切成 N 段
2. 逐段用 whisper 转写
3. 每段的 segments 时间轴加上偏移量（段索引 × segment_duration）
4. 拼接所有段的 full_text + segments

耗时估算：118 分钟 / 5 分钟段 = 24 段 × ~100s/段 ≈ 40 分钟（small 模型 CPU）

### 画面理解工作流（VLM）

脚本只负责抽帧，VLM 理解由调用方（AI agent）执行：

1. 脚本抽帧：`--extract-frames --frame-interval 30`
2. 脚本 OCR：`--ocr`（提取 PPT 标题、代码块、字幕等内嵌文字）
3. 调用方 VLM 理解：把关键帧图片发给 vision 模型，结合 OCR 文字和转写文字，理解画面内容

```
# 调用方拿到 frames 列表后，对关键帧做 VLM 理解：
# "这张图片是视频第 {timestamp} 秒的画面，OCR 识别到文字：{texts}。
#  结合转写文字上下文，描述画面中展示的内容。"
```

### LLM 校对工作流

whisper 对专有名词识别有误（如"GStack"→"JSTARC"、"Agent"→"AZ"）。脚本输出校对提示词，调用方执行：

1. 脚本转写 + 生成提示词：`--llm-correct-prompt`
2. 调用方 LLM 执行校对：把 `llm_correct_prompt` 字段发给 LLM
3. LLM 返回校对后的纯文本

## Layer 2: agent-browser 提取页面信息 + 评论区

**使用场景：** Layer 1 的 SSR 解析失败，或需要提取评论区内容（评论里有用户反馈、补充资料链接等）。

### 页面信息提取

1. 使用 agent-browser 导航到视频 URL（浏览器能正确处理短链重定向）
2. 等待 3-5 秒让页面完全加载
3. 获取页面快照，提取标题、描述、作者等

### 评论区提取

1. 用 agent-browser 打开视频页面
2. 滚动到评论区
3. 获取快照，提取热门评论文字
4. 关注评论中的：补充资料链接、用户反馈、作者回复

```bash
agent-browser open "<视频URL>"
agent-browser wait --load networkidle
agent-browser snapshot -i
# 滚动到评论区
agent-browser scroll down 2000
agent-browser snapshot -i
```

**限制：** 此方案**无法获取视频本身的语音转写**，只能获取页面上的文字信息。

## Layer 3: WebSearch 搜索相关信息（最后手段）

当以上两层全部失败时，通过搜索引擎查找视频相关信息。

1. 从 URL 或上下文中提取视频标题关键词、作者名
2. 使用 WebSearch 搜索：`"<视频标题>" <作者名> 抖音`
3. 查找是否有文字版转载、截图、或他人整理的文字内容
4. 标注信息来源，提醒用户核对

## 完整工作流

收到抖音视频阅读需求时，按以下流程执行：

### Step 1: 识别输入

判断用户提供的链接是否为抖音视频：
- 域名包含 `douyin.com` 或 `v.douyin.com` 或 `iesdouyin.com`
- 或用户明确提到"抖音视频""抖音链接"

从用户输入中提取纯 URL（脚本会自动正则提取，支持分享文本）。

### Step 2: 判断视频类型选择参数

- **短视频（<5分钟）**：默认参数即可（转写前 5 分钟）
- **长视频（≥5分钟）**：加 `--full-transcribe`（分段完整转写）
- **教学类视频（含 PPT/代码）**：加 `--extract-frames --ocr`（提取画面内嵌文字）
- **需要高质量文案**：加 `--llm-correct-prompt`（生成校对提示词）

### Step 3: 执行 Layer 1

```bash
python3 /workspace/skills/douyin-reader/scripts/douyin_reader.py "<URL>" [参数] --json
```

### Step 4: 画面理解（如需）

如果脚本输出了 frames 和 ocr_results：
1. 选取关键帧（有 OCR 文字的帧优先）
2. 用 VLM 理解画面内容
3. 结合转写文字和 OCR 文字，构建完整内容理解

### Step 5: LLM 校对（如需）

如果脚本输出了 llm_correct_prompt：
1. 把提示词发给 LLM
2. LLM 返回校对后的文案
3. 用校对后的文案替换原始转写文字

### Step 6: 评论区提取（如需）

如果用户需要评论区的用户反馈或补充资料：
1. 用 agent-browser 打开视频页面
2. 滚动到评论区提取

### Step 7: 输出结果

向用户呈现视频内容，包含：
- **标题** / **作者** / **时长** / **统计**
- **语音转写文字**（带时间轴 segments）
- **画面内嵌文字**（OCR 结果，按时间戳组织）
- **画面理解**（VLM 分析，如执行了 Step 4）
- **评论区**（如执行了 Step 6）
- **内容来源标注**

如果用户要求"学习""总结""提取知识点"，进一步：
- 提炼核心观点（3-5 个要点）
- 识别视频结构（开头钩子 → 主体内容 → 结尾行动号召）
- 标注可行动的信息
- 结合转写文字 + OCR 文字 + 画面理解，构建完整知识图谱

## 内容沉淀指导

当用户要求"内容沉淀"时，将提取的内容整理为结构化文档：

```
# [视频标题]

## 基本信息
- 作者：xxx
- 链接：xxx
- 时长：xxx
- 数据：点赞 xx | 评论 xx | 分享 xx

## 核心内容
[语音转写的精华提炼，已 LLM 校对]

## 画面关键信息
[OCR 提取的 PPT 标题、代码块、架构图文字，按时间戳组织]
- [00:30] GStack 架构图：Master/Worker/Skill 三层
- [05:15] 七步冲刺工作流：思考→策划→开发→复查→测试→误数→反馈

## 关键要点
1. [要点1]
2. [要点2]
3. [要点3]

## 可行动信息
- [具体可执行的建议或步骤]

## 评论区精华
- [用户反馈/补充资料链接/作者回复]

## 来源标注
- 内容来源：语音转写(small模型,已LLM校对) + OCR(rapidocr) + 画面理解(VLM) + 评论区(agent-browser)
- 获取时间：[日期]
- ⚠️ 如某维度未获取，标注缺失原因
```

## 失败处理

如果三层全部失败：

1. 明确告知用户："抖音视频内容获取失败，可能是反爬限制或视频不可用"
2. 提供替代方案：
   - "请在抖音 APP 中打开视频，手动复制文案内容给我"
   - "如果视频有文字版描述，请直接粘贴"
3. 不要静默返回空内容或伪造结果

## 常见问题

**Q: 为什么 SSR 解析是首选而不是 yt-dlp？**
A: 2026-07-11 实测，yt-dlp 对抖音短链接解析失败（重定向到首页），长链接需要 Cookie。而 iesdouyin SSR 解析无需 Cookie/Key，直接从分享页的 SSR JSON 拿到无水印直链。SSR 方案借鉴自 yzfly/douyin-mcp-server v1.2.1（Apache 2.0）。

**Q: 能获取视频语音转写吗？**
A: 能。Layer 1 的 SSR 解析下载视频后，用 ffmpeg 抽音频 + openai-whisper 转写。实测 small 模型 1 分钟音频 21.9s 出 393 字文案，语义清晰，带时间轴 segments。

**Q: 长视频怎么完整转写？**
A: 用 `--full-transcribe`，脚本按 `--segment-duration`（默认 300 秒）分段，逐段转写后时间轴偏移拼接。118 分钟视频 ≈ 24 段 × 100s/段 ≈ 40 分钟（small 模型 CPU）。

**Q: 能提取画面里的文字吗？**
A: 能。`--extract-frames --ocr` 抽帧后用 rapidocr 识别 PPT 标题、代码块、字幕等内嵌文字。实测对教学视频效果良好。

**Q: 能理解画面内容吗？**
A: 脚本只负责抽帧，VLM 理解由调用方（AI agent）执行。脚本输出帧图片路径列表 + OCR 文字，调用方把关键帧发给 vision 模型理解画面。

**Q: 转写准确率如何？**
A: small 模型语义清晰，但专有名词有误。用 `--llm-correct-prompt` 生成校对提示词，调用方 LLM 校对后质量显著提升。

**Q: 如何只获取元数据不做语音转写？**
A: 使用 `--skip-transcribe` 参数，仅解析+下载。

**Q: 抖音改版导致 SSR 解析失效怎么办？**
A: 降级到 Layer 2（agent-browser 提取页面文字）。同时可关注 yzfly/douyin-mcp-server 的更新。
