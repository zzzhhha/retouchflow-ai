# RetouchFlow AI

RetouchFlow AI is an experimental local AI retouching workflow assistant for
Lightroom Classic, Photoshop, and local pixel-based photo editing.

中文主页：[README.md](README.md)

Status: `v0.1-alpha`. The core workflow is usable for testing, but the project is
not yet a polished commercial retouch product. Treat Photoshop automation,
Action hooks, local masks, and pixel retouching as early integrations that need
your own validation before production use.

The plug-in keeps Lightroom responsible for RAW decoding, Develop rendering, preview generation, and final export. The local service analyzes exported previews, generates bounded Develop parameters, reviews proof images, and returns small correction deltas when a batch needs a second pass.

## Project Layout

```text
lightroom-plugin/
  AIAutoRetouch.lrplugin/   Lightroom Classic Lua plug-in

local-ai-service/
  app/                      FastAPI service and parameter engine
  styles/                   Style preset constraints
  tests/                    Unit tests for parameter logic
```

## MVP Workflow

```text
Select RAW files in Lightroom Classic
-> Plug-in exports low-res previews
-> Local service builds a group style and per-photo parameters
-> Plug-in applies Develop presets to each photo
-> Plug-in exports proof JPGs
-> Local service reviews before/after proofs
-> Plug-in applies one or two bounded correction passes
-> Plug-in exports high-quality JPG/TIFF sources for retouch
-> Local service runs local pixel retouch or Photoshop retouch
-> Plug-in imports retouched files for manual review
-> Run AI Export again to confirm and copy final files
```

## Quick Start

1. Create and activate a Python virtual environment.
2. Install the local service dependencies:

```powershell
pip install -r .\local-ai-service\requirements.txt
```

3. Start the service:

```powershell
.\scripts\start-service.ps1
```

4. Open the local dashboard:

```text
http://127.0.0.1:8765/dashboard
```

5. Optional: copy example config files when you need external AI or Photoshop
   Action hooks:

```powershell
Copy-Item .\local-ai-service\config\settings.example.json .\local-ai-service\config\settings.json
Copy-Item .\local-ai-service\config\photoshop_actions.example.json .\local-ai-service\config\photoshop_actions.json
```

Both generated config files are ignored by git.

6. In Lightroom Classic, open `File > Plug-in Manager...`, click `Add`, and choose:

```text
lightroom-plugin/AIAutoRetouch.lrplugin
```

7. Select photos in Library, then run:

```text
Library > Plug-in Extras > AI Auto Retouch...
```

## New Edit Controls

The Lightroom plug-in now sends these editing controls to the local service:

```text
照片场景：自动识别、人像、风景、花卉、草地树木、森林、城市建筑、日落晚霞、夜景、美食、静物等
审美风格：自然、糖水片、质感片、大师风、日系清透、胶片感、商业干净、高级灰等
处理层级：基础修图、基础修图 + 进阶建议、基础修图 + 进阶执行
修图建议：可为空；例如“保持原比例”“不要瘦脸”“只去瑕疵”“重点增加光影”
```

The current version automatically applies bounded basic Develop parameters. Crop/recomposition and masks are reported as suggestions in the dashboard first. If a user suggestion is provided, it is passed to external AI prompts and also enforced by local fallback rules for hard constraints such as no crop, no face slimming, and no skin smoothing.

## AI Config

Open:

```text
http://127.0.0.1:8765/dashboard/config
```

You can configure:

```text
provider
base URL
model
API key
enabled / disabled
```

The API key is saved locally in `local-ai-service/config/settings.json`, which is ignored by git. The dashboard only shows the masked key.

## AI Modes

The local service works without an external AI provider. By default it uses deterministic image metrics and style rules. To add a vision API later, implement `app/ai_planner.py` behind the existing `Planner` interface and keep `app/lightroom_params.py` as the final safety clamp.

## Local Region And Pixel Retouch

The service now emits per-photo `local_analysis` with detected regions and
pixel-retouch operations. Pixel-level portrait and landscape work is exposed via:

```text
POST http://127.0.0.1:8765/v1/photos/pixel-retouch
```

Details: `docs/local-region-pixel-retouch.md`.

In Lightroom, `AI Auto Retouch...` can now automatically export high-quality
JPG/TIFF retouch sources after the review pass, call either local pixel retouch
or Photoshop retouch, and import generated retouched files for manual review.
After checking them in Lightroom, run `AI Export...` again to finalize the
export directory. The optional Lightroom user suggestion is also sent to this
retouch pass.

## Photoshop Bridge

Photoshop desktop execution is available as a first-stage bridge. The local
service can create Photoshop jobs, write JSX scripts, launch the installed
Photoshop executable, and collect PSD/JPG outputs for the next review step.
The bridge can also call configured Photoshop Actions per AI operation, so
installed or recorded actions for blemish cleanup, frequency separation,
Liquify/face slimming, relight, architecture darkening, sky balance, and
foliage tone can be driven by the AI plan.

Set `AI_RETOUCH_PHOTOSHOP_EXE` if Photoshop is not installed in a standard Adobe
directory:

```powershell
$env:AI_RETOUCH_PHOTOSHOP_EXE = "C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe"
```

Details: `docs/photoshop-bridge.md`.

## Lightroom Debug

The Lightroom plug-in can show numbered workflow steps, write a debug log, and
surface invalid local-service JSON responses with URL and response previews.

Details: `docs/lightroom-debug.md`.

## Scope

The Lightroom plug-in still applies bounded Develop parameters as the default
safe path. Local region analysis, local pixel retouch, and Photoshop PSD/JPG
retouch are available as rendered-file paths. Complex Lightroom-native AI masks
and fully automatic generative edits remain deferred.

## Repository Hygiene

This repository intentionally excludes local working data:

- API keys and provider config: `local-ai-service/config/settings.json`
- local Photoshop Action config: `local-ai-service/config/photoshop_actions.json`
- batch records and previews: `local-ai-service/runs/`
- personal RAW files, PSD files, and rendered retouch outputs
- virtual environments and IDE caches

Before publishing a fork, rotate any API key that has ever been used locally and
check `git status --short` for accidental photo or credential files.
