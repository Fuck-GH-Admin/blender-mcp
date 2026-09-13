# 安装、运行与维护

## 前置条件

- Python 3.10 或更新版本；推荐使用 [uv](https://docs.astral.sh/uv/)。
- 一个与上游 `v1.0.0` Bridge 协议兼容的官方 Blender MCP Add-on，已在 Blender 中启用。
- 本次验证环境为 Blender 5.2.1 LTS。渲染引擎值使用实际 Blender 枚举
  `BLENDER_EEVEE` 和 `CYCLES`。

项目将 MCP Python SDK 锁定到 `>=1.2.0,<2`。这不是任意保守限制：上游 `v1.0.0` 使用的
`mcp.server.fastmcp` import 在 SDK 2.x 中已不存在。

## 安装与启动

在仓库根目录执行：

```bash
uv sync --project mcp
uv run --project mcp super-blender-mcp --profile core
```

Add-on 默认只在 `localhost:9876` 监听。多 Blender、旧 Add-on 或测试实例并存时，两个
进程必须指定相同的端口：

```bash
BLENDER_MCP_HOST=localhost BLENDER_MCP_PORT=9987 \
  uv run --project mcp super-blender-mcp --profile core
```

Server 从不扫描 `9876–9890`。显式端口是为了防止 Agent 操作到错误的 `.blend`。

常用启动形式：

```bash
# 官方对照组
uv run --project mcp super-blender-mcp --profile official

# 完整工具面
uv run --project mcp super-blender-mcp --profile full

# 仅受信任的本机调试；不提供隔离
uv run --project mcp super-blender-mcp --profile core --unsafe-python

# 本地 HTTP（默认 127.0.0.1:8000）
uv run --project mcp super-blender-mcp --transport http --host 127.0.0.1 --port 8000
```

## MCP client 配置

将绝对路径替换为本仓库的实际路径：

```toml
[mcp_servers.super_blender]
command = "uv"
args = ["run", "--project", "/absolute/path/to/super-blender-mcp-next/mcp", "super-blender-mcp", "--profile", "core"]
env = { BLENDER_MCP_HOST = "localhost", BLENDER_MCP_PORT = "9876" }
```

先启动 Blender 和 Add-on，再启动 client。连接失败时依次检查：Add-on 是否已启用、端口是否
一致、端口是否被旧 Add-on 占用、以及 client 是否在可访问当前 Python 环境中运行。

## 验证

无需 Blender 的回归测试：

```bash
uv run --project mcp --with pytest python -m pytest \
  tests/test_mcp_server.py tests/test_tool_listing.py tests/test_agent_layer.py \
  tests/test_polyhaven_pack.py tests/test_context_benchmark.py \
  tests/test_agent_experience.py -q
```

真实 Blender 端到端测试必须使用隔离端口，不能终止或复用用户现有的 9876 Add-on。最低
验证路径是：创建对象、变换、增添 modifier、创建/分配材质、配置/预览渲染、查询对象，
再验证 `execute_blender_code` 拒绝 `import os`。

## 快速启动 Blender（demo-blender）

`make demo-blender`（可用 `PORT=`、`BLENDER_BIN=`、`DEMO_HOME=` 覆盖）把端到端验证过的
样板流程固化成一条命令：构建 addon zip、装入隔离的 `BLENDER_USER_RESOURCES` 目录、
在给定端口启动 background Blender 并等待端口可达。它只打印启动说明与 PID，不作为
安全边界。

## 本地指标与 benchmark

默认没有遥测、没有网络上报，也不会写文件。只有显式设置下列变量时才会在该路径追加
JSONL：

```bash
BLMCP_METRICS_PATH=/absolute/path/to/metrics.jsonl \
  uv run --project mcp super-blender-mcp --profile core
```

启动记录包含 `tool_schema`、工具数、schema UTF-8 bytes 与 `bytes / 4` 的稳定 token
估算。每次调用记录参数/结果字节数、生成 Python 字符数、`ok` 结果与 `duration_ms`
（毫秒，区分慢操作与快操作；run-report 的 per-tool 行汇总 total 与 max）。该 token 数是用于
相对比较的估算，不等于任一模型的实际 tokenizer 结果。

离线 schema tax 对照（不需要 Blender，直接在进程内测量各 profile 的冻结 schema）：

```bash
uv run --project mcp python -m blmcp.metrics.context_benchmark schema-tax
```

当前参考值（随文档改动会漂移，以命令输出为准）：

```text
profile   tools  schema_bytes  est_tokens
official  26     16863         4216
core      24     23252         5813
creator   31     27074         6769
asset     26     24737         6185
full      43     32589         8148
```

两个 Poly Haven pack 工具只增加约 0.4k token，而完整官方工具面比默认 core 多出 19 个
工具；这说明"按 profile 裁剪 + pack"比"全部塞进 core"更符合 context-efficiency 目标。

聚合与对照已记录的运行：

```bash
# 汇总单次运行：每工具调用数、成功/失败、token 估算、总 context 增长
uv run --project mcp python -m blmcp.metrics.context_benchmark run-report metrics.jsonl

# A/B 对照（candidate 减 baseline 的差值）
uv run --project mcp python -m blmcp.metrics.context_benchmark compare baseline.jsonl candidate.jsonl
```

建议以同一任务、同一 Blender 文件、同一模型分别跑 `official`（baseline）与 `core`
（candidate）profile，并保留任务成功率和人工纠正次数，不要只比较 token。完整
Agent-in-the-loop A/B 仍需要真实 Blender 与模型；本工具负责指标与对照，不代替该流程。

## Poly Haven 缓存

pack 下载的文件默认缓存在 `~/.cache/super-blender-mcp-next/polyhaven`，可用
`BLMCP_POLYHAVEN_CACHE` 重定向。导入的图片引用缓存路径，因此不要在会话进行中删除缓存；
确定不再需要时可以整体清空目录以释放空间。

## 开发与上游同步

本仓库维护自己的功能版本和标签；上游 `v1.x.y` 标签表示 Blender 官方提交，不能复写。
同步上游时应：

1. 拉取并审阅上游标签与迁移说明。
2. 将其作为独立提交合入，不把上游改动混进 structured tools。
3. 重新运行 official profile 的快照测试和 agent layer 测试。
4. 使用隔离的真实 Blender 完成最小端到端路径。
5. 在 `CHANGELOG.md` 与兼容性记录中注明上游基线和迁移结论。

禁止将 `--unsafe-python` 作为通用兼容性修复，也不要以自动端口扫描处理连接问题。
