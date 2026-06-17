# Photoshop Bridge

The Photoshop bridge is the first desktop execution path for high-quality pixel
retouch. It keeps the local AI service as the planner and job coordinator, then
uses the installed Photoshop desktop app as an execution tool.

## Installed Photoshop

The bridge first checks `AI_RETOUCH_PHOTOSHOP_EXE`, then probes common Adobe
install locations under `Program Files`.

Set the environment variable when Photoshop is installed somewhere else:

```powershell
$env:AI_RETOUCH_PHOTOSHOP_EXE = "C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe"
```

## Photoshop Action Hooks

The bridge can call Photoshop Actions after creating each AI operation layer.
This is the recommended next step for high-quality work because Photoshop
Actions can hold real retouch procedures such as healing, frequency separation,
Liquify, and tonal layers.

Create:

```text
local-ai-service/config/photoshop_actions.json
```

You can start from:

```text
local-ai-service/config/photoshop_actions.example.json
```

`photoshop_actions.json` is a local machine config and is ignored by git. Keep
third-party `.atn` packs out of the repository unless their license is clear and
you actually need to redistribute them.

Example:

```json
{
  "enabled": true,
  "actions": {
    "skin_smoothing": {
      "set": "AI Retouch",
      "action": "Skin Smoothing",
      "required": false
    },
    "face_slimming": {
      "set": "AI Retouch",
      "action": "Subtle Face Slimming",
      "required": false
    }
  }
}
```

The keys must match AI operation types such as `blemish_cleanup`,
`skin_smoothing`, `frequency_separation`, `face_liquify`, `face_relight`,
`architecture_darken`, `sky_light_balance`, `foliage_green_boost`, and
`foliage_tone_control`. If an action is missing or fails and `required=false`,
the JSX runner records the action error in the result marker but keeps the PSD
and JPG export path alive.

For commercial retouch, record or install Actions for these operation types:

1. `blemish_cleanup`: healing/spot removal layer.
2. `frequency_separation` or `commercial_skin_retouch`: frequency separation or texture-safe skin workflow.
3. `face_liquify` or `face_slimming`: subtle Liquify/Face-Aware Liquify.
4. `face_relight`: portrait dodge and burn.
5. `architecture_darken`: masked architecture/foreground exposure reduction.
6. `foliage_green_boost` and `foliage_tone_control`: masked green/foliage color work.

Set `required=true` only when you want a missing or failed Action to fail the
whole Photoshop job. Keep it `false` while tuning the action pack.

## AI Masks

`POST /v1/photos/photoshop-retouch` creates mask assets from local region
analysis before queuing Photoshop. Masks are written under:

```text
local-ai-service/runs/{batch_id}/photoshop/masks/{photo_id}
```

Each planned operation receives `mask_path`, `mask_bbox`, and `mask` metadata
when a matching region exists. The generated JSX imports mask PNGs into the PSD
as hidden `AI mask guide - ...` layers so a retoucher can inspect or reuse them.
The current JSX runner does not convert those PNGs into Photoshop layer masks
automatically; for commercial output, the configured Actions should apply the
active layer/mask convention used by your action pack.

## Job Flow

```text
Local AI service creates a Photoshop job
-> job JSON and JSX script are written under local-ai-service/runs/{batch_id}/photoshop
-> Photoshop opens the input file and runs the JSX script
-> Photoshop saves layered PSD and flattened JPG output
-> Photoshop writes a result marker JSON
-> local service marks the job completed or failed
```

This means the user does not need to manually pass image files from step to step.
The system passes file paths through job manifests.

## API

Check bridge status:

```text
GET /v1/photoshop/status
```

The status response includes the active Photoshop executable path and Action
configuration summary.

Create a high-level AI Photoshop retouch task:

```text
POST /v1/photos/photoshop-retouch
```

Example:

```json
{
  "batch_id": "manual-ps-test",
  "photo_id": "IMG_0001",
  "input_path": "C:/path/to/input.jpg",
  "scene": "portrait",
  "aesthetic": "natural",
  "operations": ["skin_cleanup", "skin_texture_smoothing", "face_relight"],
  "user_suggestion": "保留自然肤质，只去明显瑕疵",
  "run": false
}
```

If `operations` is empty, the service uses local region analysis to choose the
Photoshop operations. Set `run=true` when you want the local service to launch
Photoshop immediately. Otherwise the job stays queued and can be picked up by
the helper script or a future UXP worker.

Create a job:

```text
POST /v1/photoshop/jobs
```

Example:

```json
{
  "batch_id": "manual-ps-test",
  "photo_id": "IMG_0001",
  "input_path": "C:/path/to/input.jpg",
  "scene": "portrait",
  "aesthetic": "natural",
  "quality_mode": "commercial",
  "operations": [
    {"type": "skin_smoothing", "target": "skin", "strength": 0.18},
    {"type": "frequency_separation", "target": "skin", "strength": 0.18},
    {"type": "face_liquify", "target": "face", "strength": 0.08},
    {"type": "face_relight", "target": "face", "strength": 0.2}
  ],
  "user_suggestion": "保留自然肤质，不要过度磨皮"
}
```

Run the queued job with the desktop Photoshop bridge:

```powershell
.\scripts\run-photoshop-job.ps1
```

Or run a specific job:

```powershell
.\scripts\run-photoshop-job.ps1 -BatchId manual-ps-test -JobId IMG_0001 -WaitSeconds 60
```

## Current Execution Scope

The current JSX runner is intentionally conservative. It creates candidate
retouch layers and exports:

- layered PSD under `runs/{batch_id}/photoshop/psd`
- flattened JPG under `runs/{batch_id}/photoshop/output`
- result marker under `runs/{batch_id}/photoshop/jobs`

The first execution layer supports:

- a blemish-cleanup candidate layer for repair operations
- a softening candidate layer for skin-smoothing operations
- a frequency-separation guide layer for commercial skin workflows
- a face-shape candidate layer for Liquify/action execution
- a local-light candidate layer for relight/dodge-burn operations
- an architecture exposure candidate layer
- sky and foliage tone candidate layers for landscape operations
- hidden AI mask guide layers imported from generated mask PNGs
- optional Photoshop Action calls per operation through `app.doAction`

High-end operations such as content-aware blemish cleanup, generative repair,
frequency separation, and Liquify/Face-Aware Liquify should be provided as
Photoshop Actions, batchPlay/UXP commands, or dedicated local model outputs.
The built-in JSX fallback is intentionally conservative and should be treated
as a PSD staging and review layer, not a guaranteed final commercial retouch.

## Recommended Next Step

Add a Photoshop action pack or UXP executor for:

1. content-aware blemish cleanup
2. masked skin smoothing with texture preservation
3. subtle face-shape warp
4. local relight layers
5. PSD layer naming and review metadata

The job format is already structured so those operations can be added without
changing Lightroom or the local AI planning API.
