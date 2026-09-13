# 变更记录

本文件记录 Super Blender MCP Next 的版本；`v1.x.y` 形式的上游 Blender MCP 标签只表示
官方源代码版本，不代表本项目的发布标签。

## 1.1.1 — 2026-09-13

依据 Agent 实战体验评审（两项真实任务、75 次工具调用的实证）落实全部八项改进：

- AX-01：新增 `execute_blender_code_unrestricted`，仅随 `--enable-unrestricted` 显式启用；
  safe guard 拒绝可信代码时不再需要重启 Server 丢失会话状态。
- AX-02：`light_create_or_update` 与新增的 `camera_create_or_update` 支持 `target` look-at；
  相机可由 structured tool 创建。
- AX-03：新增 `scene_batch`，单次往返顺序执行多项 structured operations，逐项紧凑回包、
  首错即停、与 `request_id`/`expected_revision` 语义对齐。
- AX-04：新增 `object_manage`（join / apply_transform / set_origin / shade_smooth /
  shade_flat），建模高频意图不再落入 Python fallback。
- AX-05：所有工具调用记录 `duration_ms`；run-report 按 tool 汇总 total/max。
- AX-06：fallback 成功回包附带 `scene_changed`；新增 `scene_refresh` 主动重观测并重置
  已知对象基线（不推进 revision）。
- AX-07：`make demo-blender` 一条命令完成 addon 构建、隔离安装与 background Blender 启动。
- AX-08：新增本地文件导入 pack：`import_file`（SVG/glTF/OBJ/FBX/图片），SVG 自动启用
  `io_curve_svg`。

## 1.1.0 — 2026-09-13

- 新增 Poly Haven capability pack：`polyhaven_search` 与 `polyhaven_import` 在 `asset`/
  `full` profile 注册；下载与 API 请求仅在 Server 侧进行，文件缓存在本地
  （`BLMCP_POLYHAVEN_CACHE` 可重定向），Blender 只接收导入缓存文件的受信 toolcode。
- 新增离线 benchmark 工具 `python -m blmcp.metrics.context_benchmark`：`schema-tax`
  在进程内测量各 profile 工具 schema 成本，`run-report`/`compare` 聚合与对照
  `BLMCP_METRICS_PATH` JSONL 会话；调用记录补充 `ok` 结果字段。
- 在本地 Blender 5.2.1 LTS（background 模式、隔离 HOME 与端口）完成真机端到端验证：
  官方工具 40 项全过；structured tools 与 Poly Haven 贴图/HDRI/模型导入 21/21 通过。
  据此修复 Poly Haven 对接的两个真实问题：`info` 端点的资产 `type` 为整数枚举
  （0/1/2）；模型 `gltf` 条目是引用外部文件的 JSON、API 不提供配套文件，模型导入改用
  自带 blend 文件 append。
- 使用本插件完成 Noto Emoji U+1F416 的 SVG → 3D 模型实战（导入、挤出、材质、打光、
  渲染全链路），并将过程中发现的操作层问题整理为
  Agent 实战体验评审（AX-01～AX-08）；
  可复现脚本与证据（渲染图、.blend、会话 metrics）收入 `examples/emoji_3d/`。
- 文档补充 pack 安全边界（第三方元数据按 prompt injection 面处理）与 benchmark 用法。

## 1.0.0 — 2026-09-09

基线为 Blender 官方 MCP `v1.0.0`（`03004fd0216bfe5e0a3d9ac9b47d5efadc3d78c4`）。

- 新增固定 profile：`official`、`core`、`creator`、`asset`、`full`。
- 默认 `core` 新增紧凑观察、对象、modifier、材质、相机、灯光和同步预览渲染等 structured tools。
- 新增 Server-local session object ID、revision、`expected_revision` 和 `request_id` 去重回包。
- 为 agent profile 的交互式和后台 Python escape hatch 增加保守 AST 安全策略；官方 profile 保留上游行为。
- 新增显式启用、仅写本地 JSONL 的 schema/call context 指标。
- 增加 profile、agent layer 与上游 baseline 的回归测试，并在 Blender 5.2.1 LTS 隔离端口完成端到端验证。
- 补充架构、操作手册、API 契约与限制说明。
