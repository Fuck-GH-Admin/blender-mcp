# Emoji 3D 化示例与评审证据

用本插件把 Noto Emoji **U+1F416（🐖 PIG）** 的 SVG 做成 3D 模型的完整可复现案例，同时是
[Agent 实战体验评审](../../docs/agent-experience-review.md)（AX-01～AX-08）的实证材料：
评审中引用的 safe guard 拦截、相机创建断层、设置序列往返等证据全部来自运行本脚本的过程。

## 文件

| 文件 | 说明 |
| --- | --- |
| `build_pig_3d.py` | 构建脚本：起隔离 Blender → SVG 曲线导入/挤出/合并/上材质 → 结构化工具打光渲染 |
| `emoji_u1f416_pig.png` | 最终渲染（1024×1024，Cycles CPU，48 samples） |
| `emoji_u1f416_pig.blend` | 保存的场景（2m 分层浮雕模型、材质、相机、灯光、渲染设置齐全） |
| `metrics.jsonl` | 三次迭代的 `BLMCP_METRICS_PATH` 会话记录（51 次调用，含调试期预期失败） |

## 运行

前置：Blender 5.1+（验证环境 5.2.1 LTS），noto-emoji 的 SVG（脚本默认取工作区
`../test/noto-emoji/svg/emoji_u1f416.svg`，可用 `NOTO_EMOJI_SVG` 指定任意 emoji）。

```bash
git clone --depth 1 https://github.com/googlefonts/noto-emoji ../test/noto-emoji
python examples/emoji_3d/build_pig_3d.py
```

路径、端口、server 启动命令均可用环境变量覆盖（见脚本头部 docstring）。产物写在
脚本所在目录，重复运行会覆盖。
