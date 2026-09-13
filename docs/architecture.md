# 架构与边界

## 设计目标

Super Blender MCP Next 是官方 Blender MCP `v1.0.0` Server 的兼容扩展层。它解决的是
Agent 使用“自由编写 `bpy` 代码”时的工具选择成本、无效往返和不稳定回包问题，而不是
替换 Blender 或重新实现官方 Bridge。

第一阶段的原则是 Official-first：保持官方 Add-on、TCP 协议和官方工具模块，所有新增
语义能力都在 MCP Server 中实现。因此，正常情况下无需修改或重装官方 Add-on。

## 分层

```text
MCP client
  │ stdio / 可选 streamable HTTP
  ▼
Super Blender MCP Next Server
  ├─ 固定 profile 的官方工具集合
  ├─ structured operation 层（参数校验、revision、轻量 delta）
  ├─ capability pack providers（Poly Haven；网络仅在 Server 侧）
  ├─ safe fallback code AST guard
  └─ 可选本地 JSONL 指标
  │ localhost TCP、NUL 分隔 JSON、type=execute
  ▼
官方 Blender MCP Add-on
  │ bpy
  ▼
Blender 场景
```

Bridge 是短连接请求/响应模式。Server 通过官方 `send_code` helper 与 Add-on 通信；
structured operation 发送的是项目内受审查的 toolcode，并要求 Add-on 以 strict JSON
回包。用户或 Agent 临时生成的 Python 只能经 escape hatch 发送。

## Profile

Profile 在 Server 启动时确定，不能由单个 MCP client 动态切换：

| Profile | 工具内容 | Python 回退行为 |
| --- | --- | --- |
| `official` | 原版官方工具与原版 prompt | 完全保留上游行为，不加 AST guard |
| `core`（默认） | 紧凑官方观察/文档工具 + 19 个 structured tools | 默认安全检查 |
| `creator` | core + 官方 UI 导航、窗口截图和渲染工具 | 默认安全检查 |
| `asset` | core + Poly Haven pack + 本地导入 pack（`import_file`） | 默认安全检查 |
| `full` | 全部官方工具 + structured tools + Poly Haven pack | 默认安全检查 |

`official` 是回归和 A/B benchmark 的对照组，不能将它解释为安全 profile。

`--enable-unrestricted` 会在 agent profile 中额外注册 `execute_blender_code_unrestricted`
（跳过 AST guard、无任何安全策略）。它解决的是 AX-01 的逃生口问题：safe guard 拒绝某段
可信代码时，无需重启 Server 即可执行，同时不牺牲其余会话的默认保护。该工具默认关闭，
永远不会出现在未显式启用的会话里。

## 状态、ID 与幂等

成功的 structured mutation 会获得递增的 `revision` 与 `action_id`，并返回只含受影响
对象的 `delta`。写操作可带：

- `expected_revision`：若不等于当前 Server revision，则返回 `STALE_SCENE`，提示先调用
  `scene_summary`。
- `request_id`：同一 Server 生命周期内重试相同 ID 会返回缓存的原结果，并标记
  `status: "already_completed"`；缓存上限为 128 条。

fallback `execute_blender_code` 的成功回包附带 `scene_changed`（对比执行前后对象名集合），
并把 Server 的已知对象基线同步到真实场景——因此 fallback 改动会即时可见，无需额外查询。
`scene_refresh` 负责带外改动（人工编辑、其他客户端直接写 Add-on）：它重新观察场景、返回
created/deleted 名单并重置基线。两者都不推进 `revision`——revision 只统计 Server 自己
提交的 mutation。

对象引用优先使用回包中的 session ID（例如 `obj_7fd1...`）；Server 将其映射回对象名。
ID 不会写入 `.blend`，Server 重启后即失效。任何接收对象引用的 structured tool 都仍可
直接传名称作为回退。

`revision` 不是 Blender 的全局事务版本：手动编辑、其他 MCP Server、Undo/Redo 和 Add-on
之外的变更不会自动增加它。它只用于发现当前 Server 已知的并发写入。

## 回包契约

成功查询通常为：

```json
{"ok": true, "revision": 3, "objects": [{"id": "obj_...", "name": "Cube"}]}
```

成功写入增加 `action_id`、`changed` 和可选 `delta`。失败统一为：

```json
{
  "ok": false,
  "revision": 3,
  "error": {
    "code": "STALE_SCENE",
    "message": "Scene revision does not match the expected revision.",
    "recoverable": true,
    "suggested_action": "scene_summary"
  }
}
```

常见错误码：`STALE_SCENE`（重新观察后重试）、`SAFE_CODE_REJECTED`（改用 structured
tool 或重写代码）、`BLENDER_EXECUTION_FAILED`（检查 Blender/Add-on/参数）与
`INVALID_BRIDGE_RESULT`（Bridge 回包不符合 structured 契约）。

## 安全模型

结构化工具的 Blender-side toolcode 是本仓库代码的一部分；它不是由 client 参数拼接出的
任意 Python。`core`、`creator`、`asset`、`full` 中两个 Python escape hatch 都默认经过
保守 AST 检查，阻止文件、进程、网络、动态执行、dunder 属性、Add-on 操作及
handlers/timers。它允许完成建模所需的 `bpy`、`bmesh`、`mathutils` 等有限导入。

这只是策略检查，**不是沙箱，也不能抵御恶意本地代码**。`--unsafe-python` 或
`BLMCP_UNSAFE_PYTHON=1` 会关闭检查，只适用于信任边界清晰的本机调试。官方 `official`
profile 按兼容承诺保留原始全权限 escape hatch。

默认 stdio 没有监听网络端口。可选 HTTP 默认绑定 `127.0.0.1`；不要把 `--host` 改成
可路由地址，因为继承的官方 HTTP 兼容层启用了宽松 CORS，且并非安全网关。

capability pack 是唯一会主动访问外网的组件：Poly Haven 的 API 请求与文件下载全部在
MCP Server 进程内完成，进入 Blender 的只有本地已缓存文件的导入 toolcode。资产元数据
（名称、分类）是第三方文本，属于潜在的 prompt injection 面，因此搜索结果只返回少量
字段并限制条数。下载缓存在本地目录，可用 `BLMCP_POLYHAVEN_CACHE` 重定向；导入的图片
引用缓存路径，删除缓存会使旧 `.blend` 中的贴图路径失效。

## 明确未实现的能力

- 多实例自动发现/端口扫描；必须用 `BLENDER_MCP_HOST` 与 `BLENDER_MCP_PORT` 显式选定。
- 永久对象 ID、人类编辑 revision、Undo checkpoint；这些需要 Add-on Level 2 改造。
- 异步渲染任务队列；`render_preview` 是同步操作。
- Poly Haven 之外的其他资产 provider（Sketchfab、Hyper3D 等）尚未接入。
