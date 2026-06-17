# MVP Test Plan

## Service Tests

Run:

```powershell
.\scripts\run-tests.ps1
```

Expected result: all parameter clamp and mapping tests pass.

## Lightroom Manual Test

1. Start the local service:

```powershell
.\scripts\start-service.ps1
```

2. Add `lightroom-plugin/AIAutoRetouch.lrplugin` in Lightroom Classic Plug-in Manager.
3. Select 3-5 RAW files in Library.
4. Run `Library > Plug-in Extras > AI Auto Retouch...`.
   Choose a photo scene, aesthetic style, edit level, and optionally enter a
   user suggestion such as `保持原比例，不要瘦脸，只去瑕疵`.
5. Confirm:

```text
- Preview JPGs are exported to the temp batch directory.
- The service writes analyze/review JSON under local-ai-service/runs/{batch_id}.
- The dashboard shows scene, aesthetic, crop suggestions, and advanced suggestions.
- The dashboard shows the user suggestion when one was entered.
- Lightroom creates an "AI Before {batch_id}" snapshot.
- Develop settings visibly change in Lightroom.
- Plug-in metadata fields contain batch ID, style, score, and params JSON.
- The dashboard shows the batch at `http://127.0.0.1:8765/dashboard`.
```

6. Run `Library > Plug-in Extras > AI Export...` with a final export directory set.
7. Leave pixel retouch and review import enabled.
8. Confirm:

```text
- High-quality sources are exported under the temp batch directory.
- The service writes pixel-retouch JSON under local-ai-service/runs/{batch_id}.
- Pixel-retouch request manifests include the same `user_suggestion` value.
- Retouched JPG files are written under the temp batch directory.
- Lightroom imports and selects the retouched JPG files for review.
- The dashboard batch summary shows final export status as waiting for manual confirmation.
```

9. Inspect the imported retouched JPG files in Lightroom.
10. Run `Library > Plug-in Extras > AI Export...` again and confirm final export.
11. Confirm JPG files appear in the selected export directory and the dashboard shows finalized export status.

## Known MVP Limits

- The plug-in uses Lightroom Develop presets for global settings.
- Pixel retouch currently writes separate rendered JPG files instead of Lightroom-native masks.
- Complex Lightroom AI masks and generative edits remain out of scope.
- The local service uses deterministic metrics until a vision model is wired into `Planner`.
