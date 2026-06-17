# RetouchFlow AI

RetouchFlow AI 是一个实验性的本地 AI 修图流程助手，目标是把 Lightroom Classic、Photoshop 和本地像素处理串成一套可自动执行、可人工确认的批量修图工作流。

当前状态：`v0.1-alpha`。核心流程已经可以用于本地测试，但还不是成熟的商业级成片系统。Photoshop 自动化、动作包调用、本地蒙版分析和像素精修都属于早期集成，需要你在自己的图片和机器环境里验证后再用于正式生产。

## 项目定位

RetouchFlow AI 不是要替代 Lightroom 或 Photoshop，而是让 AI 参与修图决策，并把这些决策转成可执行的本地流程：

- Lightroom 负责 RAW 解码、基础参数、预览渲染和最终导出。
- 本地服务负责图片分析、参数规划、审核判断、局部区域识别和任务编排。
- Photoshop 可作为高质量精修执行器，用于 PSD/JPG 输出和人工复核。
- 本地像素引擎可在不启动 Photoshop 的情况下执行保守的局部处理。

## 主要功能

- Lightroom Classic 插件：批量选择照片后一键进入 AI Auto Retouch 流程。
- 本地 FastAPI 服务：默认可不接外部 AI，使用本地规则和图像指标分析。
- 可选外部 AI：可配置兼容 OpenAI 风格的接口，让模型参与修图方案理解和建议。
- 用户修图建议：支持输入“保持比例”“不要瘦脸”“重点压天空高光”“草地更绿”等自然语言建议。
- 基础修图：自动生成曝光、对比、高光、阴影、白平衡、饱和、锐化、降噪等受限参数。
- 进阶建议/执行：生成局部调整、暗角、HSL、裁剪、场景化优化等进阶方案。
- 本地区域分析：识别人脸、皮肤、天空、草地、暗部、高光等局部区域。
- 像素精修接口：支持保守的皮肤、脸型和风景局部增强输出。
- Photoshop 桥接：创建 Photoshop JSX 任务，输出分层 PSD 和精修 JPG。
- Photoshop Actions 钩子：可把去瑕疵、磨皮、液化、局部光影等动作包接入 AI 计划。
- 控制台预览：支持查看修图前、基础修后、精修后三阶段对比。
- Debug 状态：Lightroom 插件可显示步骤、错误位置和本地服务响应。

## 目录结构

```text
lightroom-plugin/
  AIAutoRetouch.lrplugin/   Lightroom Classic Lua 插件

local-ai-service/
  app/                      FastAPI 服务和修图规划逻辑
  config/                   示例配置文件
  styles/                   风格约束和预设
  tests/                    单元测试

docs/                       工作流、Photoshop、Lightroom SDK 和发布说明
scripts/                    启动和测试脚本
```

## 工作流程

```text
在 Lightroom Classic 里选择 RAW 照片
-> 插件导出低分辨率预览图
-> 本地服务分析图片和用户建议
-> 生成整组风格和单张修图参数
-> 插件把基础 Develop 参数应用到 Lightroom
-> 插件导出 proof JPG
-> 本地服务审核修图前后效果
-> 必要时执行一到两轮受限修正
-> Lightroom 导出高质量 JPG/TIFF 给精修流程
-> 本地像素引擎或 Photoshop 执行精修
-> 精修结果导回 Lightroom 供人工确认
-> 最后再次执行 AI Export 输出最终文件
```

## 快速开始

1. 创建并激活 Python 虚拟环境。

2. 安装本地服务依赖：

```powershell
pip install -r .\local-ai-service\requirements.txt
```

3. 启动本地服务：

```powershell
.\scripts\start-service.ps1
```

4. 打开本地控制台：

```text
http://127.0.0.1:8765/dashboard
```

5. 在 Lightroom Classic 中打开：

```text
File > Plug-in Manager... > Add
```

选择：

```text
lightroom-plugin/AIAutoRetouch.lrplugin
```

6. 在图库中选择照片，然后运行：

```text
Library > Plug-in Extras > AI Auto Retouch...
```

## 可选配置

如果需要外部 AI 或 Photoshop Actions，可以从示例文件复制本地配置：

```powershell
Copy-Item .\local-ai-service\config\settings.example.json .\local-ai-service\config\settings.json
Copy-Item .\local-ai-service\config\photoshop_actions.example.json .\local-ai-service\config\photoshop_actions.json
```

这两个真实配置文件默认被 `.gitignore` 忽略，不应该提交到仓库。

也可以使用环境变量，避免把密钥和本机路径写入 JSON：

```powershell
$env:AI_RETOUCH_API_KEY = "your-api-key"
$env:AI_RETOUCH_PHOTOSHOP_EXE = "C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe"
```

## AI 模式

RetouchFlow AI 默认可以离线运行，不强制依赖外部模型：

- 本地规则模式：根据亮度、高光、暗部、饱和度、色温、锐度等指标生成安全参数。
- 外部 AI 模式：把图片指标、场景、用户建议和约束传给模型，让模型参与规划。
- 混合模式：即使外部 AI 失败，也会回退到本地规则，避免流程中断。

所有 Lightroom 参数都会经过安全边界限制，避免 AI 直接输出过激参数。

## Photoshop 桥接

Photoshop 桥接用于高质量精修阶段。它会：

- 生成 Photoshop 任务 JSON。
- 写入 JSX 脚本。
- 启动本机 Photoshop。
- 创建候选图层、蒙版参考层和动作钩子。
- 保存 PSD 和 JPG。
- 把结果交回 Lightroom 预览和人工确认。

如果 Photoshop 不在常见 Adobe 安装目录中，请设置：

```powershell
$env:AI_RETOUCH_PHOTOSHOP_EXE = "C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe"
```

Photoshop Actions 需要你自己录制或安装。示例配置在：

```text
local-ai-service/config/photoshop_actions.example.json
```

真实配置文件：

```text
local-ai-service/config/photoshop_actions.json
```

不会提交到仓库。

## 当前限制

- 这是 alpha 版本，重点是跑通工作流，不保证所有机器和 Photoshop 版本都有一致表现。
- Lightroom SDK 对原生 AI 蒙版/生成式编辑的自动化能力有限，本项目当前主要走渲染图和 Photoshop/像素引擎路径。
- 本地人脸、皮肤、天空、草地等检测是轻量规则和图像分析，不等同于专业分割模型。
- Photoshop Actions 的质量取决于你安装或录制的动作包。
- 商业级磨皮、液化和修瑕疵仍需要动作包、人工复核或后续更强的执行引擎。

## 隐私和仓库卫生

不要提交以下内容：

- `local-ai-service/config/settings.json`
- `local-ai-service/config/photoshop_actions.json`
- API Key、Relay Token 或其他密钥
- `local-ai-service/runs/`
- Lightroom 目录、RAW 原片、PSD、proof 图、最终成片
- `.venv/`、IDE 缓存、日志文件

发布前建议执行：

```powershell
git status --short
```

并参考：

```text
docs/release-checklist.md
```

## 许可证

本项目使用 MIT License。

Copyright (c) 2026 zzzhhha
