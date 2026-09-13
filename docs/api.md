# Structured Tool API

这些工具在 `core`、`creator`、`asset` 和 `full` profile 中可用。`official` profile 不包含
它们。所有坐标为 Blender 单位，旋转均为弧度；色彩为 0–1 的 RGB/RGBA 数组。

## 通用写入参数与结果

除查询工具外，每个 structured tool 都接受可选 `expected_revision` 与 `request_id`。
前者用于避免基于过期观察写入；后者用于在网络重试时保持一次逻辑动作只提交一次。

成功写入至少返回 `ok: true`、`action_id` 和 `revision`，通常还含 `changed`、对象
`target` 或 `delta`。对象 ID 仅在 Server 存活期间有效；可以在所有对象参数中传名称。
错误包络与限制见[架构文档](architecture.md#回包契约)。

## 观察

| 工具 | 参数 | 用途 |
| --- | --- | --- |
| `scene_summary` | 无 | 场景对象计数、选择集、活动对象、相机、模式和渲染引擎的紧凑摘要。 |
| `search_objects` | `name_pattern?`, `object_type?`, `collection?`, `material?`, `visible?`, `limit=20` | 返回同时匹配的少量对象；在大场景编辑前先缩小目标。 |
| `scene_refresh` | 无 | 重新观察场景并返回 created/deleted 名单，专抓 Server 带外的改动（人工编辑、其他客户端）。fallback Python 的改动已由 `scene_changed` 标记并自动同步基线，无需 refresh。不推进 `revision`。 |

## 对象

| 工具 | 必填参数 | 可选参数 |
| --- | --- | --- |
| `object_create` | `primitive`：`CUBE`、`UV_SPHERE`、`ICO_SPHERE`、`CYLINDER`、`CONE`、`TORUS`、`PLANE`、`MONKEY` | `name`, `location`, `rotation`, `scale` |
| `object_transform` | `object` | `location`, `rotation`, `scale`, `space`（`WORLD`/`LOCAL`，默认 `WORLD`） |
| `object_delete` | `object` | 无 |
| `object_duplicate` | `object` | `new_name`, `linked_data=true`；默认共享源 mesh/curve data |
| `object_set_properties` | `object` | `name`, `visible`, `render_visible`, `display_type`（`TEXTURED`、`SOLID`、`WIRE`、`BOUNDS`） |
| `object_parent` | `object` | `parent`（省略/`null` 清除父级）、`keep_world_transform=true` |
| `object_manage` | `object`, `action` | `action`：`join`（把 `others` 合入 `object`，仅 mesh）、`apply_transform`（`apply_location/apply_rotation/apply_scale`）、`set_origin`（`origin`：`GEOMETRY`/`CURSOR`/`GEOMETRY_CENTER`）、`shade_smooth`/`shade_flat`。 |

## Modifier 与材质

| 工具 | 必填参数 | 可选参数与限制 |
| --- | --- | --- |
| `modifier_manage` | `object`, `action`：`add`/`update`/`remove`/`apply` | `add` 必须提供 `type`（例如 `BEVEL`）；其余 action 必须提供 `modifier`；`properties` 只接受可写标量或向量属性。 |
| `material_create_or_update` | `name` | `base_color`, `metallic`, `roughness`, `alpha`, `emission`, `emission_strength`；编辑 Principled BSDF。 |
| `material_assign` | `object`, `material` | `slot=0`；默认替换 mesh 的第一个槽位。 |

## 相机、灯光与渲染

| 工具 | 必填参数 | 可选参数 |
| --- | --- | --- |
| `camera_create_or_update` | `name` | `location`, `rotation`, `target`（瞄准世界坐标点，与 `rotation` 互斥）、`lens`（焦距，毫米）；场景无相机时自动设为活动相机。 |
| `camera_frame` | `objects` | `camera`, `view`（`FRONT`/`BACK`/`LEFT`/`RIGHT`/`TOP`/`THREE_QUARTER`）、`padding=0.15` |
| `light_create_or_update` | `name` | `type`（`POINT`/`SUN`/`SPOT`/`AREA`，默认 `AREA`）、`energy`, `color`, `location`, `rotation`, `size`, `target`（与 `rotation` 互斥） |
| `render_configure` | 无 | `engine`（`BLENDER_EEVEE`/`CYCLES`）、`resolution_x`, `resolution_y`, `samples`, `transparent`；只改提供的字段。 |
| `render_preview` | `output_path` | `max_dimension=512`, `samples=16`；同步输出一个低分辨率预览。 |

`render_preview` 会修改渲染设置并写入调用方提供的文件路径。请将输出路径限制在预期的项目或
临时目录；它不是持久化渲染队列。

## 批量与逃生口

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `scene_batch` | `operations`：`[{"tool": ..., "arguments": {...}}]` | 单次往返顺序执行注册表内的 structured operations（上限 32 项），逐项返回紧凑结果；首个失败默认中止并给出 `failed_at`（`stop_on_error=false` 可继续）。每项可自带 `request_id`/`expected_revision`。 |
| `execute_blender_code_unrestricted` | `code` | 仅当 Server 以 `--enable-unrestricted` 启动时注册。完全跳过 AST guard，无任何安全策略；只用于受信任的开发者会话。 |

## Poly Haven 资产包

仅在 `asset` 和 `full` profile 注册。这是 pack 机制的首个实现：外部 API 请求与下载都在
MCP Server 内完成，Blender 只接收导入本地缓存文件的受信 toolcode，因此不需要修改 Add-on。

| 工具 | 必填参数 | 可选参数与限制 |
| --- | --- | --- |
| `polyhaven_search` | 无 | `query`（空串列出前几个）、`asset_type`（`hdri`/`texture`/`model`，默认 `hdri`）、`limit=5`（上限 10）；只返回 `id`、`name` 与最多三个 `categories`。 |
| `polyhaven_import` | `asset_id`（来自 `polyhaven_search`） | `object`（仅 texture：把材质赋给该对象第一个槽位）、`resolution`（`1k`/`2k`/`4k`/`8k`，默认 `2k`）、`expected_revision`、`request_id`。 |

导入语义按资产类型区分：HDRI 写入当前 world 的环境贴图；texture 创建与资产同名的
Principled 材质并连接可用的 base color / roughness / normal 贴图；model 追加（append）
Poly Haven 自带的 blend 文件（其 `gltf` 条目是引用外部 bin/贴图的小 JSON，API 不提供
配套文件，因此不使用）。下载文件缓存在本地（`BLMCP_POLYHAVEN_CACHE` 或
`~/.cache/super-blender-mcp-next/polyhaven`），重复导入不会重复下载。

同一 pack 机制下还注册 `import_file(path, format)`（`asset`/`full` profile）：导入本地
SVG（自动启用 `io_curve_svg`）、glTF/GLB、OBJ、FBX 几何体，或把图片加载为 image
datablock。Server 侧校验路径存在性与扩展名匹配。

错误码：`ASSET_FETCH_FAILED`（API 或下载失败，网络与分辨率问题都归入此码，消息中会列出
可用分辨率）、`ASSET_FILE_MISSING`（缓存文件在导入前消失）、`IMPORT_FAILED`（Blender
导入器报错）。资产元数据是第三方文本，结果字段刻意保持最少。

## Python escape hatch

`execute_blender_code(code, debug=false)` 作用于已连接的交互式 Blender；
`execute_blender_code_for_cli(blend_file, code)` 会启动后台 Blender。两者在 agent
profile 默认受 AST guard 保护，且都要求将 JSON 可序列化字典赋给 `result`（后台工具的
外层回包再包裹为 `{ "ok": true, "result": ... }`）。交互式 fallback 的成功回包附带
`scene_changed`（对比执行前后对象名集合），并把 Server 的已知对象基线同步到真实场景；
后台 CLI 路径不附带。fallback 改动不推进 `revision`；`scene_refresh` 用于发现带外改动。

当 structured tools 无法表达操作时，先 `search_api_docs` 或 `search_manual_docs`，再使用
最小 Python 回退。不要用 escape hatch 承担常见的对象、材质、灯光或预览任务。
