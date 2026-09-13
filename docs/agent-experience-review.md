# Agent 实战体验评审与改进清单

> 日期：2026-09-13
> 评审人：驱动本项目的 Agent 本身（Claude/ZCode），在完成两项真实任务后复盘。
> 性质：这是一份**带实证的体验评审**，不是愿望清单。每个问题都有：真实会话中的复现证据、
> 设计文档依据、涉及代码位置，以及建议方案。状态统一记录在文末索引表中。

## 1. 证据来源

所有问题均在以下真实会话中遇到并记录，证据可复现：

| 会话 | 环境 | 内容 | 记录 |
| --- | --- | --- | --- |
| 结构化层端到端验证 | Blender 5.2.1 LTS，background 模式，隔离 HOME + 端口 9987 | structured tools 全量 + Poly Haven 贴图/HDRI/模型导入，21/21 通过 | `test/emoji-output/` 同款驱动脚本；会话 metrics 见文末 |
| Noto Emoji 3D 化 | Blender 5.2.1 LTS，background 模式，隔离 HOME + 端口 9988 | 将 `test/noto-emoji/svg/emoji_u1f416.svg`（U+1F416 🐖）构建为 3D 模型并渲染 | `test/emoji-output/build_pig_3d.py`（完整构建脚本）、`test/emoji-output/metrics.jsonl` |

两项任务合计 75 次工具调用（24 + 51），其中 fallback Python 生成约 4.2k token，
safe guard 触发 2 次、执行失败 3 次——每一次失败都是下述问题的直接证据。

## 2. 结论摘要

| ID | 问题 | 优先级 | 状态 |
| --- | --- | --- | --- |
| [AX-01](#ax-01) | 缺 `execute_blender_code_unrestricted`，逃生口是全有或全无的重启 | P1 | 1.1.1 已实现 |
| [AX-02](#ax-02) | 相机/灯光无 `look_at` 语义，且无法创建相机 | P1 | 1.1.1 已实现 |
| [AX-03](#ax-03) | 无批量操作工具，设置序列被迫多次往返 | P1 | 1.1.1 已实现 |
| [AX-04](#ax-04) | 对象级操作（join/apply/origin/convert/shade）无 structured 覆盖 | P2 | 1.1.1 已实现（convert 暂缺） |
| [AX-05](#ax-05) | 指标缺单次调用耗时，run-report 只有会话首尾时间差 | P2 | 1.1.1 已实现 |
| [AX-06](#ax-06) | fallback 变更不推进 revision、不产生 delta | P2 | 1.1.1 已实现（scene_changed + scene_refresh） |
| [AX-07](#ax-07) | Blender 侧安装/启动全靠手工 shell 操作 | P3 | 1.1.1 已实现 |
| [AX-08](#ax-08) | 本地文件导入（SVG/GLB/FBX）无工具覆盖 | P3 | 1.1.1 已实现 |

## 3. 问题明细

### AX-01

**问题**：`execute_blender_code` 的 AST guard 是 agent profile 的唯一 Python 通道，
被拒后的唯一出路是带 `--unsafe-python` 重启整个 server——丢失全部会话状态（session ID、
revision、request 缓存），且把所有工具同时置于无保护状态。

**实证**：emoji 任务中 guard 两次拦截：

```text
SAFE_CODE_REJECTED: Line 2: Import of 'addon_utils' is not allowed in safe mode
SAFE_CODE_REJECTED: Line 9: '__import__' is not allowed in safe mode
```

拦截正确（白名单见 `mcp/blmcp/security/safe_code.py:21` 与 `safe_code.py:22`），但启用
SVG 导入器这类开发者级可信操作只能绕行：先在 Blender 外探明模块名，再硬编码
`bpy.ops.preferences.addon_enable(module="io_curve_svg")` 用纯 bpy 通过。若模块名无法
预知，safe mode 内将无解。

**设计依据**：设计文档 §9 明确规划了职责分离——structured tools 走受信 toolcode、
`execute_blender_code` 默认 safe mode、用户明确需要完整能力时提供
`execute_blender_code_unrestricted` 或 `--unsafe-python`。当前只实现了中间层。

**建议方案**：新增 `execute_blender_code_unrestricted(code)` 工具，仅注册于显式启动参数
（如 `--enable-unrestricted`，默认关闭），`destructiveHint=True` 且 description 注明信任
要求。不动现有 guard 逻辑。

**涉及代码**：`mcp/blmcp/agent_ops/_bridge.py:90`（`execute_fallback_code` 的
`unsafe_python` 分支）、`mcp/blmcp/tools/execute_blender_code.py:29`、
`mcp/blmcp/settings.py`（新增开关）。

### AX-02

**问题**：相机与灯光只有"摆放"没有"瞄准"语义；且没有任何工具能创建相机。

**实证**：emoji 任务中给 KeyLight 定向只能手算欧拉角 `[0.9, 0.0, 0.65]`
（`build_pig_3d.py` Phase C），凑错角度渲染即废；创建相机则完全绕开结构化层：

```python
bpy.ops.object.camera_add(location=(0, 0, 0))  # 只能走 fallback
```

随后才能调用 `camera_frame`——结构化工具链在自己内部断了一环。

**设计依据**：设计文档 §14 以 `camera_frame` 为"高价值语义工具"范例（替代 bbox 数学与
transform Python）；§24 将相机/灯光列入 core。`look_at` 是同一原则的直接延伸。

**建议方案**：`light_create_or_update` 与新增的 `camera_create_or_update` 增加
`target: [x,y,z] | null` 参数（内部构造 track-to 约束或计算 rotation）；`object_create`
不宜膨胀类型枚举，相机单独建工具更符合 §58"高频意图语义化"。

**涉及代码**：`mcp/blmcp/agent_ops/light.py:25`、`mcp/blmcp/agent_ops/camera.py:25`、
新增 `camera.py` 内注册函数。

### AX-03

**问题**：常见设置序列（建地面 → 建材质 → 赋材质 → 建灯光 → 配渲染）被迫拆成多次
独立调用，每次的往返开销与工具选择成本纯属浪费。

**实证**：emoji 任务单是渲染环境就用 5 次调用；三次迭代合计 51 次调用中约 1/3 属于
此类无依赖的设置序列。metrics 显示参数 token（5928）反超结果 token（3635）——
往返频繁的直接代价。

**设计依据**：设计文档 §2 的上下文成本公式中 `C_tool_calls` 是一等项；§27/§28 要求回包
紧凑。batch 不违背紧凑原则：单次调用、逐项紧凑结果、首个错误即停。

**建议方案**：新增 `scene_batch(operations: list[{tool, arguments}])`，按顺序执行
structured tools，返回 `{results: [...], failed_at: index | null}`；只允许白名单内的
无破坏性组合（或逐项标注 destructiveHint 后放行）。注意与 `request_id` 去重语义对齐。

**涉及代码**：`mcp/blmcp/agent_ops/_bridge.py:66`（`run_mutation` 可复用为执行单元）、
新模块 `mcp/blmcp/agent_ops/batch.py`。

### AX-04

**问题**：对象级编辑操作（`transform_apply`、`join`、`origin_set`、`convert`、
`shade_smooth`）没有 structured 覆盖，全部落入 Python fallback。

**实证**：emoji 任务 Phase B 的核心流程（缩放烘焙、曲线转网格、合并、设原点、转角）
全部由约 40 行 fallback Python 完成，是本次 `execute_blender_code` 生成 token 的
最大单项来源（27 次调用合计 4229 token）。

**设计依据**：设计文档 §14 反对"bpy wrapper"，要求按意图语义化。`object_manage` 的
action 集合（join/apply/origin/shade）是建模工作流的高频意图，不是 API 转写。

**建议方案**：新增 `object_manage(object, action: "join"|"apply_transform"|"set_origin"|
"shade_smooth"|"shade_flat", others?: list, ...)`。join 的目标选择、apply 的纬度限定
在 toolcode 内处理。

**涉及代码**：新增 `mcp/blmcp/agent_ops/object_manage.py` + `_toolcode.py`，复用
`_toolcode_runtime.py` 的 `success/failure` 机制。

### AX-05

**问题**：`record_tool_call` 不记录单次调用耗时；run-report 的 `wall_time_seconds`
只是首尾时间戳之差，无法区分慢操作与快操作。

**实证**：emoji 会话 `wall_time_seconds: 487.9`——其中 `render_preview`（秒级 × 3）
与其他毫秒级调用完全不可分。设计文档 §50 将 `wall_time` 列为必须记录的指标。

**建议方案**：`record_tool_call` 增加 `duration_ms` 可选参数（调用方用 `time.monotonic`
包住 bridge 调用），JSONL 条目与 run-report 的 per-tool 行各加一列；`compare` 汇总
total/mean。

**涉及代码**：`mcp/blmcp/metrics/context.py:69`（`record_tool_call`）、各 `_mutation`
包装器（计时点）、`mcp/blmcp/metrics/context_benchmark.py:96`（聚合）。

### AX-06

**问题**：structured mutation 才推进 revision 并产生 delta（`state/runtime.py:71`）；
fallback `execute_blender_code` 修改场景后两者都不更新，Agent 基于回包建立的场景认知
会静默过期。

**实证**：端到端验证会话中，三次 Poly Haven 导入失败回包的 `revision` 恒为 10——期间
fallback 曾导入过 12 个 SVG 对象，revision 纹丝不动。文档（architecture.md 状态节）
承认此限制，但 Agent 没有任何主动同步手段。

**设计依据**：设计文档 §31 的 revision 目标是"我看到的场景是不是现在的场景"；§32 允许
Demo 用近似手段（snapshot hash）实现。

**建议方案**：最小改法是提供只读工具 `scene_refresh()`：执行一次轻量 snapshot 对比，
返回变化并重置 revision 基线；更完整的做法是 fallback 执行成功后自动附带
`scene_changed: true|false`（对比对象数与名字集合，成本低）。

**涉及代码**：`mcp/blmcp/agent_ops/_bridge.py:100`（fallback 成功路径）、
`mcp/blmcp/agent_ops/_toolcode_runtime.py:111`（`scene_snapshot` 已有现成基础）。

### AX-07

**问题**：使用前的 Blender 侧准备（构建 addon zip → 安装扩展 → 带端口启动 background
Blender）全部手工 shell 操作，两次会话各重复了一遍约 20 行样板。

**实证**：`build_pig_3d.py:60-77`（构建/安装/启动/等端口），与端到端验证脚本几乎逐行
相同。

**设计依据**：设计文档 §47 将运行时能力推迟到 Add-on Level 2——本项不违反：它是 CLI
辅助（不进 MCP 工具面），只是把验证过的流程固化。

**建议方案**：新增 Makefile 目标（如 `make demo-blender PORT=9988`）或
`super-blender-mcp --setup-blender` 子命令：构建 zip、装入隔离 `BLENDER_USER_RESOURCES`、
按给定端口启动 background Blender。文档在 operations.md 同步。

**涉及代码**：`Makefile`、`docs/operations.md`。

### AX-08

**问题**：Poly Haven pack 覆盖远程资产，但本地文件导入（SVG/GLB/FBX/图片参考）无
structured 工具，全落 fallback。

**实证**：emoji 任务整条 SVG 导入链（启用 io_curve_svg → `import_curve.svg`）走
fallback；GLB 同理（`import_scene.gltf`）。

**设计依据**：设计文档 §46 验证了 pack 机制后"再加 Sketchfab/Hunyuan"，本地导入是
同一层能力的自然组成；§58 的原则是"高频意图语义化、长尾 generic 化"。

**建议方案**：在 `asset` pack 中增加 `import_file(path, format: "svg"|"glb"|"obj"|
"fbx"|"image", ...)`：server 侧校验路径与格式，toolcode 分发到对应导入 operator。
SVG 导入需先自动启用 `io_curve_svg`（toolcode 内 `addon_enable` 不受 guard 管）。

**涉及代码**：`mcp/blmcp/providers/`（新模块）、`mcp/blmcp/profiles/__init__.py`
（pack 注册不变）。

## 4. 实证为"做得好"的部分（不要动）

- **紧凑回包有效**：两次会话结构化工具的结果 token 稳定低于参数 token，符合 §27/§28。
- **`request_id` 重放与 `expected_revision` 拒绝精准生效**：真机复验通过
  （`already_completed` 与 `STALE_SCENE` 均按契约返回）。
- **`render_preview` 的 `max_dimension` 临时覆盖设计好用**，迭代期无需反复改渲染设置。
- **错误包络的 `suggested_action` 每次都把操作引回正轨**（如 2D 曲线报错后指向
  `search_api_docs`）。
- **safe guard 拦截本身是正确行为**（见 AX-01：问题在逃生口缺失，不在 guard）。

## 5. 建议实施顺序

1. **AX-02**（look_at + 相机创建）——改动最小，每次使用受益。
2. **AX-01**（unrestricted 逃生口）——补齐设计文档既定方案。
3. **AX-03**（batch）——收益最大，需先定白名单语义。
4. AX-05 → AX-04 → AX-06 随后；AX-07/AX-08 穿插进行。

## 6. 追溯索引

| 主题 | 设计文档（`Super-Blender-MCP-Next-Agent-Native-Design.md`） | 代码 |
| --- | --- | --- |
| safe mode 与逃生口 | §9、§44 | `mcp/blmcp/security/safe_code.py`、`mcp/blmcp/agent_ops/_bridge.py` |
| 语义化工具原则 | §14、§24、§58 | `mcp/blmcp/agent_ops/camera.py`、`light.py` |
| 上下文成本模型 | §2、§27、§28 | `mcp/blmcp/metrics/context.py` |
| revision 与状态 | §31、§32 | `mcp/blmcp/state/runtime.py`、`_toolcode_runtime.py` |
| benchmark 指标 | §50、§51 | `mcp/blmcp/metrics/context_benchmark.py` |
| pack 与导入 | §46、§58 | `mcp/blmcp/providers/polyhaven/` |
| Level 2 边界 | §47 | `docs/architecture.md`（明确未实现的能力） |

证据文件已随仓库分发于 [`examples/emoji_3d/`](../examples/emoji_3d/)：
`build_pig_3d.py`（可复现构建脚本）、`metrics.jsonl`（会话指标）、
`emoji_u1f416_pig.png`（渲染产物）、`emoji_u1f416_pig.blend`（模型场景）。
