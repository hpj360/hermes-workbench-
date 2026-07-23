---
name: Agent Browser
description: A fast Rust-based headless browser automation CLI with Node.js fallback that enables AI agents to navigate, click, type, and snapshot pages via structured commands.
read_when:
  - Automating web interactions
  - Extracting structured data from pages
  - Filling forms programmatically
  - Testing web UIs
metadata: {"clawdbot":{"emoji":"🌐","requires":{"bins":["node","npm"]}}}
allowed-tools: Bash(agent-browser:*)
---

# Browser Automation with agent-browser

## Installation

### npm recommended

```bash
npm install -g agent-browser
agent-browser install
agent-browser install --with-deps
```

### From Source

```bash
git clone https://github.com/vercel-labs/agent-browser
cd agent-browser
pnpm install
pnpm build
agent-browser install
```

## Quick start

```bash
agent-browser open <url>        # Navigate to page
agent-browser snapshot -i       # Get interactive elements with refs
agent-browser click @e1         # Click element by ref
agent-browser fill @e2 "text"   # Fill input by ref
agent-browser close             # Close browser
```

## Core workflow

1. Navigate: `agent-browser open <url>`
2. Snapshot: `agent-browser snapshot -i` (returns elements with refs like `@e1`, `@e2`)
3. Interact using refs from the snapshot
4. Re-snapshot after navigation or significant DOM changes

## Commands

### Navigation

```bash
agent-browser open <url>      # Navigate to URL
agent-browser back            # Go back
agent-browser forward         # Go forward
agent-browser reload          # Reload page
agent-browser close           # Close browser
```

### Snapshot (page analysis)

```bash
agent-browser snapshot            # Full accessibility tree
agent-browser snapshot -i         # Interactive elements only (recommended)
agent-browser snapshot -c         # Compact output
agent-browser snapshot -d 3       # Limit depth to 3
agent-browser snapshot -s "#main" # Scope to CSS selector
```

### Interactions (use @refs from snapshot)

```bash
agent-browser click @e1           # Click
agent-browser dblclick @e1        # Double-click
agent-browser focus @e1           # Focus element
agent-browser fill @e2 "text"     # Clear and type
agent-browser type @e2 "text"     # Type without clearing
agent-browser press Enter         # Press key
agent-browser press Control+a     # Key combination
agent-browser keydown Shift       # Hold key down
agent-browser keyup Shift         # Release key
agent-browser hover @e1           # Hover
agent-browser check @e1           # Check checkbox
agent-browser uncheck @e1         # Uncheck checkbox
agent-browser select @e1 "value"  # Select dropdown
agent-browser scroll down 500     # Scroll page
agent-browser scrollintoview @e1  # Scroll element into view
agent-browser drag @e1 @e2        # Drag and drop
agent-browser upload @e1 file.pdf # Upload files
```

### Get information

```bash
agent-browser get text @e1        # Get element text
agent-browser get html @e1        # Get innerHTML
agent-browser get value @e1       # Get input value
agent-browser get attr @e1 href   # Get attribute
agent-browser get title           # Get page title
agent-browser get url             # Get current URL
agent-browser get count ".item"   # Count matching elements
agent-browser get box @e1         # Get bounding box
```

### Check state

```bash
agent-browser is visible @e1      # Check if visible
agent-browser is enabled @e1      # Check if enabled
agent-browser is checked @e1      # Check if checked
```

### Screenshots & PDF

```bash
agent-browser screenshot          # Screenshot to stdout
agent-browser screenshot path.png # Save to file
agent-browser screenshot --full   # Full page
agent-browser pdf output.pdf      # Save as PDF
```

### Video recording

```bash
agent-browser record start ./demo.webm    # Start recording (uses current URL + state)
agent-browser click @e1                   # Perform actions
agent-browser record stop                 # Stop and save video
agent-browser record restart ./take2.webm # Stop current + start new recording
```

Recording creates a fresh context but preserves cookies/storage from your session. If no URL is provided, it automatically returns to your current page. For smooth demos, explore first, then start recording.

### Wait

```bash
agent-browser wait @e1                     # Wait for element
agent-browser wait 2000                    # Wait milliseconds
agent-browser wait --text "Success"        # Wait for text
agent-browser wait --url "/dashboard"    # Wait for URL pattern
agent-browser wait --load networkidle      # Wait for network idle
agent-browser wait --fn "window.ready"     # Wait for JS condition
```

### Mouse control

```bash
agent-browser mouse move 100 200      # Move mouse
agent-browser mouse down left         # Press button
agent-browser mouse up left           # Release button
agent-browser mouse wheel 100         # Scroll wheel
```

### Semantic locators (alternative to refs)

```bash
agent-browser find role button click --name "Submit"
agent-browser find text "Sign In" click
agent-browser find label "Email" fill "user@test.com"
agent-browser find first ".item" click
agent-browser find nth 2 "a" text
```

### Browser settings

```bash
agent-browser set viewport 1920 1080      # Set viewport size
agent-browser set device "iPhone 14"      # Emulate device
agent-browser set geo 37.7749 -122.4194   # Set geolocation
agent-browser set offline on              # Toggle offline mode
agent-browser set headers '{"X-Key":"v"}' # Extra HTTP headers
agent-browser set credentials user pass   # HTTP basic auth
agent-browser set media dark              # Emulate color scheme
```

### Cookies & Storage

```bash
agent-browser cookies                     # Get all cookies
agent-browser cookies set name value      # Set cookie
agent-browser cookies clear               # Clear cookies
agent-browser storage local               # Get all localStorage
agent-browser storage local key           # Get specific key
agent-browser storage local set k v       # Set value
agent-browser storage local clear         # Clear all
```

### Network

```bash
agent-browser network route <url>              # Intercept requests
agent-browser network route <url> --abort      # Block requests
agent-browser network route <url> --body '{}'  # Mock response
agent-browser network unroute [url]            # Remove routes
agent-browser network requests                 # View tracked requests
agent-browser network requests --filter api    # Filter requests
```

### Tabs & Windows

```bash
agent-browser tab                 # List tabs
agent-browser tab new [url]       # New tab
agent-browser tab 2               # Switch to tab
agent-browser tab close           # Close tab
agent-browser window new          # New window
```

### Frames

```bash
agent-browser frame "#iframe"     # Switch to iframe
agent-browser frame main          # Back to main frame
```

### Dialogs

```bash
agent-browser dialog accept [text]  # Accept dialog
agent-browser dialog dismiss        # Dismiss dialog
```

### JavaScript

```bash
agent-browser eval "document.title"   # Run JavaScript
```

### State management

```bash
agent-browser state save auth.json    # Save session state
agent-browser state load auth.json    # Load saved state
```

## Example: Form submission

```bash
agent-browser open https://example.com/form
agent-browser snapshot -i
# Output shows: textbox "Email" [ref=e1], textbox "Password" [ref=e2], button "Submit" [ref=e3]

agent-browser fill @e1 "user@example.com"
agent-browser fill @e2 "password123"
agent-browser click @e3
agent-browser wait --load networkidle
agent-browser snapshot -i  # Check result
```

## Example: Authentication with saved state

```bash
# Login once
agent-browser open https://app.example.com/login
agent-browser snapshot -i
agent-browser fill @e1 "username"
agent-browser fill @e2 "password"
agent-browser click @e3
agent-browser wait --url "/dashboard"
agent-browser state save auth.json

# Later sessions: load saved state
agent-browser state load auth.json
agent-browser open https://app.example.com/dashboard
```

## Sessions (parallel browsers)

```bash
agent-browser --session test1 open site-a.com
agent-browser --session test2 open site-b.com
agent-browser session list
```

## JSON output (for parsing)

Add `--json` for machine-readable output:

```bash
agent-browser snapshot -i --json
agent-browser get text @e1 --json
```

## Debugging

```bash
agent-browser open example.com --headed              # Show browser window
agent-browser console                                # View console messages
agent-browser console --clear                        # Clear console
agent-browser errors                                 # View page errors
agent-browser errors --clear                         # Clear errors
agent-browser highlight @e1                          # Highlight element
agent-browser trace start                            # Start recording trace
agent-browser trace stop trace.zip                   # Stop and save trace
agent-browser record start ./debug.webm              # Record from current page
agent-browser record stop                            # Save recording
agent-browser --cdp 9222 snapshot                    # Connect via CDP
```

## Troubleshooting

- If the command is not found on Linux ARM64, use the full path in the bin folder.
- If an element is not found, use snapshot to find the correct ref.
- If the page is not loaded, add a wait command after navigation.
- Use --headed to see the browser window for debugging.

## Options

- --session <name> uses an isolated session.
- --json provides JSON output.
- --full takes a full page screenshot.
- --headed shows the browser window.
- --timeout sets the command timeout in milliseconds.
- --cdp <port> connects via Chrome DevTools Protocol.

## Notes

- Refs are stable per page load but change on navigation.
- Always snapshot after navigation to get new refs.
- Use fill instead of type for input fields to ensure existing text is cleared.

## Reporting Issues

- Skill issues: Open an issue at https://github.com/TheSethRose/Agent-Browser-CLI
- agent-browser CLI issues: Open an issue at https://github.com/vercel-labs/agent-browser

---

## 标准工作流

### Step 1: 打开页面

```bash
agent-browser open <url>
```

**CHECKPOINT**: 页面是否成功加载？
- 检查方式：`agent-browser get url` 确认 URL 正确
- 失败处理：如果超时，增加 `--timeout 30000`；如果被拦截，尝试 `--headed` 查看实际情况

### Step 2: 获取页面快照

```bash
agent-browser snapshot -i
```

**CHECKPOINT**: 是否获取到交互元素？
- 成功标志：输出包含 `[ref=e1]` 等元素引用
- 失败处理：如果输出为空，页面可能还在加载，执行 `agent-browser wait 2000` 后重试

### Step 3: 执行交互

```bash
agent-browser click @e1
agent-browser fill @e2 "text"
```

**CHECKPOINT**: 操作是否生效？
- 检查方式：重新 `snapshot -i` 确认状态变化
- 失败处理：如果元素不存在，重新获取快照；如果点击无反应，尝试 `agent-browser wait @e1` 等待元素可交互

### Step 4: 验证结果

```bash
agent-browser get text @e1
agent-browser wait --url "/success"
```

**CHECKPOINT**: 结果是否符合预期？
- 成功标志：页面显示预期内容或跳转到预期 URL
- 失败处理：检查 `agent-browser errors` 查看页面错误

---

## 失败处理流程

### 常见失败场景

| 场景 | 原因 | 处理方式 |
|------|------|---------|
| 元素不存在 | 页面未加载完成 | `agent-browser wait @e1` 或 `wait --load networkidle` |
| 点击无反应 | 元素被遮挡或不可交互 | `agent-browser scrollintoview @e1` 后重试 |
| 超时错误 | 页面响应慢 | 增加 `--timeout 60000` |
| 验证码拦截 | 网站有反爬机制 | 使用 `--headed` 手动完成验证，或 `state save` 保存登录态 |
| 登录失效 | Session 过期 | `state load auth.json` 恢复登录态 |
| 网络错误 | 连接问题 | 检查网络，使用 `agent-browser network requests` 查看请求状态 |

### 失败时的用户通知

当浏览器自动化失败时，**明确告知用户**：

1. 具体失败原因（不是笼统的"出错了"）
2. 当前页面状态（URL、标题、可见元素）
3. 建议的修复方案

**示例**：
```
❌ 元素 @e3 点击失败：元素不可见

当前页面：https://example.com/form
页面标题：表单提交

建议修复：
- 执行 `agent-browser scrollintoview @e3` 滚动到元素
- 或使用 `agent-browser wait @e3` 等待元素可交互

是否需要我尝试这些方案？
```

---

## 反例与黑名单

### 禁止行为

| 禁止 | 原因 | 替代方案 |
|------|------|---------|
| ❌ 不获取快照直接操作 | ref 可能已失效 | 每次操作前 `snapshot -i` |
| ❌ 硬编码 ref（如 @e1） | ref 随页面变化 | 从快照动态获取 ref |
| ❌ 不等待页面加载 | 元素可能不存在 | `wait --load networkidle` |
| ❌ 无限循环等待 | 可能永远不成功 | 设置 `--timeout` 上限 |
| ❌ 在无头模式下调试 | 看不到实际页面 | 使用 `--headed` 调试 |
| ❌ 忽略页面错误 | 可能导致后续失败 | 定期 `agent-browser errors` |

### 错误示例（反例）

**❌ 错误示例 1：不获取快照直接操作**

```bash
agent-browser open example.com
agent-browser click @e1  # ref 可能已过期
```

**问题**：页面加载后 ref 会变化，直接使用旧 ref 会失败

**✅ 正确做法**：

```bash
agent-browser open example.com
agent-browser wait --load networkidle
agent-browser snapshot -i  # 获取最新 ref
agent-browser click @e1    # 使用新 ref
```

---

**❌ 错误示例 2：不处理验证码**

```bash
agent-browser open https://example.com/protected
agent-browser snapshot -i  # 返回验证码页面
agent-browser fill @e1 "data"  # 填写到验证码输入框
```

**问题**：无头模式下无法处理验证码

**✅ 正确做法**：

```bash
# 方案 1：使用 headed 模式手动完成验证
agent-browser open https://example.com/protected --headed
# 用户手动完成验证码
agent-browser state save auth.json  # 保存登录态

# 方案 2：加载已保存的登录态
agent-browser state load auth.json
agent-browser open https://example.com/protected
```

---

**❌ 错误示例 3：无限等待**

```bash
agent-browser wait @e1  # 如果元素永远不出现，会一直等待
```

**问题**：可能导致进程卡死

**✅ 正确做法**：

```bash
agent-browser wait @e1 --timeout 10000  # 最多等待 10 秒
# 或检查元素是否存在
agent-browser is visible @e1 || echo "元素不存在"
```

---

## FAQ 常见问题

**Q: 如何处理需要登录的页面？**
A: 使用 `state save` 保存登录态，后续用 `state load` 加载。首次登录可用 `--headed` 手动完成。

**Q: 如何处理动态加载的内容？**
A: 使用 `wait --text "关键词"` 或 `wait --load networkidle` 等待内容加载完成。

**Q: 如何处理 iframe 中的元素？**
A: 使用 `agent-browser frame "#iframe_id"` 切换到 iframe，操作完成后用 `frame main` 返回主框架。

**Q: 如何处理弹窗/对话框？**
A: 使用 `agent-browser dialog accept` 或 `dialog dismiss` 处理 JavaScript 弹窗。

**Q: 如何调试看不到的问题？**
A: 使用 `--headed` 显示浏览器窗口，或 `screenshot` 截图查看当前页面状态。

**Q: ref 为什么会变化？**
A: 页面导航或 DOM 更新后，元素的 ref 会重新分配。每次页面变化后都需要重新 `snapshot`。

**Q: 如何处理多标签页？**
A: 使用 `agent-browser tab` 系列命令管理多标签页，`tab 2` 切换到第二个标签页。

**Q: 如何模拟移动端访问？**
A: 使用 `agent-browser set device "iPhone 14"` 设置设备模拟。

**Q: 如何处理文件上传？**
A: 使用 `agent-browser upload @e1 file.pdf` 上传文件，@e1 是 file input 元素的 ref。

**Q: 如何获取页面中的所有链接？**
A: 使用 `agent-browser snapshot` 获取完整页面结构，或 `agent-browser eval "Array.from(document.querySelectorAll('a')).map(a=>a.href)"` 执行 JavaScript 提取。
