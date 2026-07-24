# Loop: test-mp-claim-ok

## Pattern
Multi-Perspective Analysis
N 个 Agent 从不同视角并行分析同一标的，synthesizer 汇总成报告。适合分析类任务

## Stage (分阶段上线)
**当前阶段: l2_assist**

| 阶段 | 能力 | 状态 |
|------|------|------|
| L1 只报告 | 各视角只读分析，汇总报告（不修改代码） |  |
| L2 辅助修复 | 各视角并行分析 + synthesizer 综合结论（含明确评级） | ✓ 当前 |
| L3 无人值守 | 无人值守并行分析 + 自动归档（需 denylist 保护敏感路径） |  |

## 目标定义（四步框架）
1. **完成标准（可机器验证）**:
   - TODO: 定义什么叫"做完了"

2. **边界条件（Harness约束，不能怎么做）**:
   - 禁止删除文件
   - 禁止修改denylist中的路径: auth/, payment/, security/, .env, *.key
   - TODO: 补充其他约束

3. **降级方案（失败怎么办）**:
   - 2轮后仍未完成 → 列出未解决项，交给用户决策

4. **目标分层**:
   - 全局约束: 不破坏现有功能，所有测试通过
   - 当前任务: TODO

## Maker/Checker 分离
- **Planner**: 分析状态，生成本轮执行计划
- **Generator (builder)**: 执行具体任务（有Write/Edit工具）
- **Evaluator (checker)（独立）**: 验证结果（无Write/Edit工具，工具级硬隔离）

### 关键原则：不过滤
编排器必须把checker的完整失败报告**原样转发**给builder，不要自己解读或过滤。
builder需要原始错误信息（行号、堆栈轨迹、中间输出）来定位根因。
总结会丢失关键细节，浪费整整一轮循环。

### 报告格式
- builder汇报: 改了什么 / 修改文件 / 本地检查结果
- checker报告: ALL GREEN + 逐项通过证明 / FAILED + file:line - 什么坏了 - 哪个检查抓到的

## Denylist（高风险路径，L3也不能碰）
- auth/
- payment/
- security/
- .env
- *.key

## 停止规则（七条刹车条件）
1. ALL GREEN：所有检查通过 → 停止
2. 轮次用尽：达到2轮上限 → 停止，升级
3. 预算耗尽：token 预算用尽 → 停止，升级（由 record_round 状态机处理）
4. 超出能力边界：外部依赖问题 → 停止，报告阻塞点（前置于回归）
5. 回归：修复导致新失败且有持续失败 → 停止，升级
6. 同一失败连续两轮：builder在猜 → 停止，升级
7. 无实质进展：连续2轮失败数未减且失败集合完全更换 → 停止，拆分任务

详见 stop-rules.md
