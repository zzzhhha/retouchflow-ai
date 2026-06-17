# Local AI Service

This FastAPI service analyzes Lightroom-exported preview JPGs and returns bounded Lightroom Develop parameters.

Status: alpha. The API and Lightroom workflow are usable for local testing, but
Photoshop automation and local pixel retouching should be validated on your own
images before production use.

## Start

```powershell
pip install -r .\local-ai-service\requirements.txt
uvicorn app.main:app --app-dir .\local-ai-service --host 127.0.0.1 --port 8765
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Dashboard:

```text
http://127.0.0.1:8765/dashboard
```

## Local Config

Real local config files are ignored by git. Create them from examples only when
needed:

```powershell
Copy-Item .\local-ai-service\config\settings.example.json .\local-ai-service\config\settings.json
Copy-Item .\local-ai-service\config\photoshop_actions.example.json .\local-ai-service\config\photoshop_actions.json
```

Use `AI_RETOUCH_API_KEY` and `AI_RETOUCH_PHOTOSHOP_EXE` environment variables
when you do not want credentials or executable paths written to local JSON.

AI configuration:

```text
http://127.0.0.1:8765/dashboard/config
```

Useful JSON endpoints:

```text
http://127.0.0.1:8765/api/status
http://127.0.0.1:8765/api/config
http://127.0.0.1:8765/api/runs
http://127.0.0.1:8765/api/events
POST http://127.0.0.1:8765/v1/photos/pixel-retouch
POST http://127.0.0.1:8765/v1/photos/photoshop-retouch
GET  http://127.0.0.1:8765/v1/photoshop/status
```

## Current Planner

The first implementation is deterministic and does not require an external model:

- `image_metrics.py` extracts exposure, highlight/shadow clipping, saturation, warmth, and sharpness proxies.
- `lightroom_params.py` applies scene presets, aesthetic presets, per-image corrections, and strict parameter clamps.
- `ai_planner.py` returns basic edits, crop/recomposition suggestions, and advanced mask/mixer suggestions.
- `review.py` compares before/after proofs and returns bounded correction deltas.
- `local_regions.py` detects local regions such as face, skin, sky, foliage,
  highlights, and shadows.
- `pixel_retouch.py` writes a separate retouched image for conservative skin,
  face-shape, and landscape-light operations.
- `photoshop_retouch.py` turns the same AI plan into Photoshop jobs with mask
  assets, PSD/JPG outputs, and optional Photoshop Actions.

The service interface is intentionally stable so a vision model can replace or augment `Planner.analyze()` later without changing the Lightroom plug-in.
