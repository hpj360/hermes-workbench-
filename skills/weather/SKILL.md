---
name: weather
description: Get current weather and forecasts (no API key required). 当用户询问天气、天气预报、某地气温、需要出行穿衣建议时使用此 skill。无需 API key，免费且响应快。
homepage: https://wttr.in/:help
metadata: {"clawdbot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
---

# Weather

两个免费天气服务，无需 API key，即装即用。

## 服务选择策略

| 优先级 | 服务 | 适用场景 |
|--------|------|---------|
| Layer 1 | wttr.in | 快速单行天气、快速查询 |
| Layer 2 | Open-Meteo | 需要 JSON 结构化数据、需要精确坐标 |

## 标准工作流

### Step 1: 理解用户需求

用户可能询问：
- **当前天气**：`伦敦现在天气如何？`
- **今日预报**：`明天北京需要带伞吗？`
- **多日预报**：`上海这周天气怎么样？`
- **特定参数**：`纽约现在的温度和湿度？`

**CHECKPOINT**: 用户是否提供了地点？
- 是：继续
- 否：尝试从当前工作目录推断；无法推断时询问用户

### Step 2: 选择查询方式

#### Layer 1: wttr.in（首选）

**快速单行**（最适合日常查询）：
```bash
curl -s "wttr.in/London?format=3"
# 输出: London: ⛅️ +8°C
```

**紧凑格式**（含更多信息）：
```bash
curl -s "wttr.in/London?format=%l:+%c+%t+%h+%w"
# 输出: London: ⛅️ +8°C 71% ↙5km/h
```

**完整预报**（多日+详细）：
```bash
curl -s "wttr.in/London?T"
```

**格式代码**：
| 代码 | 含义 | 示例 |
|------|------|------|
| `%c` | 天气状况 | ⛅️ ☀️ 🌧️ |
| `%t` | 温度 | +8°C |
| `%h` | 湿度 | 71% |
| `%w` | 风速 | ↙5km/h |
| `%l` | 位置 | London |
| `%m` | 月相 | 🌕 |

**常用参数**：
- 空格编码：`wttr.in/New+York`
- 机场代码：`wttr.in/JFK`
- 公制单位：`?m` | 英制：`?u`
- 仅今天：`?1` | 仅当前：`?0`
- 下载 PNG：`curl -s "wttr.in/Berlin.png" -o /tmp/weather.png`

#### Layer 2: Open-Meteo（备用）

当需要 JSON 结构化数据时使用：
```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&current_weather=true"
```

**特点**：
- 完全免费，无 rate limit
- 返回 JSON，适合程序化处理
- 需要知道地点的经纬度（可配合地理编码 API 使用）

**常用参数**：
```
latitude, longitude        # 经纬度
current_weather=true      # 当前天气
hourly=temperature_2m   # 每小时温度
daily=temperature_2m,precipitation_sum  # 每日预报
timezone=auto           # 自动时区
```

**API 文档**：https://open-meteo.com/en/docs

### Step 3: 格式化输出

向用户呈现天气信息时，使用结构化格式：

```
🌤️ 伦敦天气预报

当前：⛅️ +8°C | 湿度 71% | 风速 5km/h ↙
穿衣建议：建议穿外套，早晚较凉

今日：☀️ → 🌤️ | 高温 12°C / 低温 5°C
明天：🌧️ | 高温 10°C / 低温 4°C | 降雨概率 60%
后天：⛅️ | 高温 11°C / 低温 6°C
```

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| curl 请求超时 | 网络问题 | 增加超时参数 `--max-time 10`；或切换到 Open-Meteo |
| wttr.in 返回错误 | 服务不可用 | 降级到 Layer 2 Open-Meteo |
| 地点无法识别 | 拼写错误或非标准地名 | 尝试替代名称；使用 Open-Meteo + 经纬度查询 |
| 温度显示为 `?` | 未知地点或 API 问题 | 尝试 `wttr.in/<城市>+<国家>` 格式 |
| Open-Meteo 无数据 | 经纬度超出范围 | 检查坐标是否正确（纬度 -90~90，经度 -180~180） |
| 非拉丁字符地点 | wttr.in 不支持中文 | URL 编码或使用拼音/英文名 |

### 失败时的用户通知

```
❌ 无法获取 "某地" 的天气信息

原因：
- wttr.in 无法识别该地点名称
- 可能是拼写错误或地名格式问题

建议：
1. 尝试用英文或拼音表示（如 "北京" → "Beijing"）
2. 告诉我具体地点名称，我来调整
3. 如果是国际城市，尝试加上国家（如 "Manchester, UK"）
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 不检查地点是否有效 | 浪费 API 调用 | 先验证地点名称可识别 |
| ❌ 对不支持的地区假装成功 | 返回错误数据 | 明确告知用户该地区不可用 |
| ❌ 使用需要 API key 的服务 | 增加用户负担 | 优先使用 wttr.in / Open-Meteo |
| ❌ 不处理中文地名 | 大多数中文地名无法识别 | 转换为拼音或英文名 |
| ❌ 无限重试失败请求 | 可能触发限流 | 最多重试 2 次，失败后明确告知用户 |

### 错误示例（反例）

**❌ 错误示例 1：不处理中文地名**

```
用户：北京今天天气怎么样？
执行：curl -s "wttr.in/北京?format=3"
结果：返回错误或空数据
```

**✅ 正确做法**：

```
用户：北京今天天气怎么样？
执行：curl -s "wttr.in/Beijing?format=3"
结果：Beijing: ⛅️ +15°C

（同时告知用户：中文字地点建议用英文名或拼音）
```

---

**❌ 错误示例 2：不检查网络问题**

```
执行：curl -s "wttr.in/London"
结果：请求超时（网络问题）
响应：没有返回任何数据
```

**✅ 正确做法**：

```
执行：curl -s --max-time 10 "wttr.in/London"
# 添加超时限制

如果超时：
1. 降级到 Open-Meteo: curl -s "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&current_weather=true"
2. 如果仍然失败，告知用户网络问题
```

---

## FAQ 常见问题

**Q: wttr.in 和 Open-Meteo 哪个更好？**
A: 日常快速查询用 wttr.in（响应快、支持自然语言地名）；需要精确数据或程序化处理用 Open-Meteo（JSON 格式、无 rate limit）。

**Q: 地点名称怎么写？**
A: wttr.in 支持英文城市名、机场代码（IATA）、地标建筑名。中文字符需要转换为拼音或英文。

**Q: 支持多长时间范围的预报？**
A: wttr.in 支持 3 天预报（今天、明天、后天）。Open-Meteo 支持 7-16 天（取决于端点）。

**Q: 可以获取历史天气数据吗？**
A: wttr.in 不支持历史数据。Open-Meteo 有历史天气端点（需要不同端点）。

**Q: 天气状况的 emoji 怎么来的？**
A: wttr.in 默认返回 emoji。如果需要纯文本，用 `format=2`（仅文字）或 `format=j1`（JSON）。

**Q: 支持农历/日出日落吗？**
A: 用 `wttr.in/London?format="%m+%S+%s"` 可获取月相、日出、日落信息。
