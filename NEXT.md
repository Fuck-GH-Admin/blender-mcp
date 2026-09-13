# Super Blender MCP Next — 1.0.0

面向通用 Agent 的 Blender 控制层。它以 Blender 官方 MCP `v1.0.0`
为底座，保留官方 Add-on 与 TCP wire protocol；新能力只加在 MCP Server
侧，因此第一阶段不修改 Blender Add-on。

基线：官方 tag `v1.0.0`（commit `03004fd0216bfe5e0a3d9ac9b47d5efadc3d78c4`）。
本机验证版本为 Blender 5.2.1 LTS。该基线实际只能使用 MCP Python SDK
1.x，所以依赖显式固定为 `mcp<2`；SDK 2.x 已移除它使用的 `FastMCP` import。

## 文档导航

- [架构与边界](docs/architecture.md)：分层、协议、状态模型和安全模型。
- [安装、运行与维护](docs/operations.md)：Client 配置、环境变量、测试、指标与发布约定。
- [Structured Tool API](docs/api.md)：所有新工具的参数、结果和错误契约。
- [上游兼容性](docs/upstream-compatibility.md)：已审阅官方 tag、迁移成本和回移准则。
- [变更记录](CHANGELOG.md)：本项目自己的版本记录；上游版本另行追踪。

## 当前能力

默认 `core` profile 保持 28 个工具：紧凑观察、官方文档/截图/escape hatch，及以下
不需要 Agent 编写 `bpy` 的 structured operations：

- `scene_summary`、`search_objects`、`scene_refresh`
- `object_create`、`object_transform`、`object_delete`、`object_duplicate`、`object_set_properties`、`object_parent`、`object_manage`
- `modifier_manage`
- `material_create_or_update`、`material_assign`
- `camera_create_or_update`、`camera_frame`、`light_create_or_update`（支持 `target` look-at）
- `render_configure`、`render_preview`
- `scene_batch`（一次往返顺序执行多项操作）

`asset` 与 `full` profile 额外注册两个 capability pack：Poly Haven（`polyhaven_search`、
`polyhaven_import`）与本地文件导入（`import_file`：SVG/glTF/OBJ/FBX/图片），API 请求与
下载都在 Server 侧完成并缓存到本地，验证了 pack 不污染 core 工具面（schema tax 参照
`docs/operations.md`）。`--enable-unrestricted` 显式启用
`execute_blender_code_unrestricted`，为可信开发者会话补齐逃生口（AX-01）。

Mutation 回包默认只给 `action_id`、session object ID、`changed`、轻量 state delta 和
revision；不会自动 dump 完整场景。对象 ID 不会写入 `.blend`，只在 MCP Server
存活期间有效，名称始终可作为回退。

`execute_blender_code` 和 `execute_blender_code_for_cli` 都是最后的 escape hatch。
core/creator/full 默认启用 AST guard，拒绝文件系统、网络、进程、动态执行和持久
handlers/timers 等模式；它不是 OS 级 sandbox。仅在受信任的本地会话中使用
`--unsafe-python` 关闭检查。

没有默认遥测。若设置 `BLMCP_METRICS_PATH=/path/to/metrics.jsonl`，Server 只会向该
本地 JSONL 文件写入启动时的 tool-schema tax，以及每次工具调用的参数/结果字节数和
一致的 token 估算值。

## 启动

先安装并启用与基线匹配的官方 MCP Add-on（`addon/blender_mcp_addon/` 或本工作区的
`mcp-1.0.0/`），保持其默认 localhost 监听。Server 使用的是实际官方环境变量名：
`BLENDER_MCP_HOST` 与 `BLENDER_MCP_PORT`，默认 `localhost:9876`。

```bash
cd mcp
uv run super-blender-mcp --profile core
```

可用 profile：

- `core`：默认，紧凑的观察 + 常用编辑工具。
- `creator`：core 加官方 UI 导航和渲染工具。
- `asset`：core 加 Poly Haven capability pack（搜索与下载导入免费 HDRI/贴图/模型）。
- `full`：所有官方工具加 Demo structured tools 和 Poly Haven pack。
- `official`：未扩展的官方工具集合，用于 benchmark 对照；保持原始 Python escape-hatch 行为。

示例 MCP client 配置：

```toml
[mcp_servers.super_blender]
command = "uv"
args = ["run", "--project", "/absolute/path/to/super-blender-mcp-next/mcp", "super-blender-mcp", "--profile", "core"]
env = { BLENDER_MCP_HOST = "localhost", BLENDER_MCP_PORT = "9876" }
```

不扫描 `9876–9890`。多 Blender 或旧 Add-on 共存时必须显式选择端口，避免连接到错误工程。
HTTP 仍为可选显式 transport；Blender bridge 不会因此暴露到网络。

## 验证

```bash
uv run --project mcp --with pytest python -m pytest \
  tests/test_tool_listing.py tests/test_agent_layer.py \
  tests/test_polyhaven_pack.py tests/test_context_benchmark.py \
  tests/test_agent_experience.py -q
```

需要真实 Blender 的端到端测试时，可将 Add-on 运行在隔离端口，并在 Server 与测试进程中
设置相同的 `BLENDER_MCP_PORT`。不要为了测试占用已有的 9876 实例。

## 已知边界与下一步

离线 schema tax 对照与 JSONL 运行聚合已经落地
（`python -m blmcp.metrics.context_benchmark`，见 `docs/operations.md`）。真机使用中
真机使用中发现的操作层改进项（AX-01～AX-08）已在 1.1.1 全部落实。剩余工作：

1. 用真实 Blender + 模型跑一次 Agent-in-the-loop 的官方/新层 A/B benchmark（对照指标
   已就绪，缺受控运行环境）。
2. 按需接入更多 capability pack（Sketchfab 等），沿用现有 provider 结构。
3. scene revision 的人类编辑跟踪、undo checkpoint、多实例发现和 persistent IDs 都需要
   Add-on Level 2 扩展，不在此阶段伪装成已完成能力。
