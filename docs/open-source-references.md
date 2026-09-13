# 开源参考实现审阅

## 结论

核心痛点已有开源实现，因而不需要先以“没有先例”为前提收集完整原始调用日志。更准确地说，
已有项目分别实现了结构化操作、细粒度状态版本、最小工具发现、安全脚本授权、快照和审计。
但没有一个能直接插入本项目的官方 `v1.0.0` Add-on/TCP Bridge：它们都携带自己的
Blender Add-on 或 controller 协议。因此它们是设计和测试参考，而不是可直接 cherry-pick
的依赖。

下列仓库已在工作区同级 `../references/` 浅克隆，固定为审阅时的 HEAD：

| 参考项目 | 固定提交 | 许可证 | 已实现的关键能力 | 采用建议 |
| --- | --- | --- | --- | --- |
| [newo-ether/blender-mcp](https://github.com/newo-ether/blender-mcp) | `c0137a30948ecfe7f7620f6a63410772cf645939` | MIT | Geometry/Shader/Compositor node graph 的 owner-aware export、`base_revision` 校验、working-copy 事务、commit/rollback、语义 diff。 | **节点图 Phase 的首选协议参考**；不要直接引入其 Add-on/telemetry/discovery 架构。 |
| [Aqua-218/Blender-MCP](https://github.com/Aqua-218/Blender-MCP) | `da23b3a2005825685eecb3b57892a0085b711125` | Apache-2.0 | typed tools、认证 controller、workspace allowlist、SQLite operations/snapshots、请求 ID、历史与 snapshot diff。 | 参考 durable operation record、快照与 mock-controller 测试；不要以它的大工具面替代当前 profile。 |
| [CallMeJones/blender-agent-bridge](https://github.com/CallMeJones/blender-agent-bridge) | `140f831689adc4571178fcf80a60d82e23c0c514` | GPL-3.0-or-later | 5 个 MCP gateway tools 的按需 discovery、可见 Commit/Revert preview、显式且可撤销的 session script trust、脱敏 JSONL audit。 | 参考最小工具面、人工确认和审计脱敏；其大型 Add-on 不能直接并入本项目。 |

## 与本项目痛点的对应关系

| 痛点 | 已有实现 | 对本项目的具体启发 |
| --- | --- | --- |
| 常见任务不应靠 Agent 生成任意 `bpy` | Aqua 的 typed tool families；CallMeJones 的 catalog + gateway | 继续扩展紧凑 structured tools，不扩张默认工具清单。 |
| 变更应可验证、可重试、能发现过期状态 | newo 的 `base_revision` 和 copy/validate/commit/rollback；Aqua 的 request/operation/snapshot 记录 | 将当前 Server-local revision 升级为“资源粒度 revision”时，以 node tree 为第一试点。 |
| 大上下文/工具面损害 Agent 选择 | CallMeJones 默认只暴露 catalog/search/schema/invoke 5 个工具；newo 提供目标子图导出 | 比起一次注册 100+ 工具，更适合渐进式 capability discovery 或细粒度 query。 |
| Python 回退缺乏清晰的人类授权 | CallMeJones 只在运行期显式 script trust 后允许完整 Python | 当前 AST guard 可保留；高风险功能应增加 Add-on 内可见、可撤销的信任授予，而不是把 guard 当成沙箱。 |
| 可审计与可复盘 | Aqua 保存 request/input/output/snapshot 元数据；CallMeJones JSONL 审计按敏感键脱敏 | 将来若采集实验日志，必须 local-only、显式 opt-in，并区分“完整研究原始数据”与“默认脱敏审计”。 |

## 已核验的源码证据

- newo 的 `blender_extension/nodes/geometry_transactions.py` 先校验 patch，再复制 node tree，
  在 working tree 应用和校验，只有最终 revision 一致才切换用户；失败路径返回 rollback
  状态与诊断。这比本项目当前的进程内递增 revision 更接近真实资源版本控制。
- Aqua 的 `mcp_server/persistence.py` 定义 operations 与 snapshots 表，`request_id` 有唯一
  约束；`mcp_server/tools/history.py` 实现操作历史和 snapshot diff；controller 协议显式带
  `auth_token`、`request_id` 和 cancel message。
- CallMeJones 的 `addon/claude_blender/audit_log.py` 本地写 JSONL，并对 `code`、`script`、
  `token`、`secret` 等字段做脱敏；`bridge_server.py` 将工具目录压缩为可按需取 schema 的
  catalog，并写入调用和 timeout 事件。

## 不应直接复制的部分

- 三个项目都不是官方 Blender MCP Add-on 的小补丁，直接合并会替换或并行另一套桥接生命周期。
- newo 明确包含 telemetry 配置；它的运行与隐私默认值不应继承到本项目。
- Aqua 的持久化会保存输入和输出；若用于真实用户会话，需要先定义保留期、加密、路径和
  prompt/code 的敏感信息政策。
- CallMeJones 的 audit log 刻意**不**保存完整源码或 token，适合默认审计，不等价于用户
  授权的实验原始数据集。

## 后续取舍

优先研究 newo 的 node patch contract（只取协议思想和测试场景），其次把 Aqua 的 durable
operation/snapshot schema 缩减到当前 structured tools。只有用户明确要求研究数据时，再
设计单独的 opt-in raw trace：记录 MCP request/response、tool schema hash、生成代码、
Blender/Add-on 版本、场景基线 hash 和渲染证据，并默认脱敏路径、凭据、聊天内容和二进制资源。
