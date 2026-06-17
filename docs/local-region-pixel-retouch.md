# Local Region And Pixel Retouch

This project now has a first-stage local region analysis and pixel-retouch path.
It is intentionally conservative: Lightroom Develop settings still handle the
safe global edit path, while pixel-level work is exposed through a separate
local service endpoint.

## Analysis Output

`Planner.analyze()` adds `local_analysis` to every `PhotoPlan`.

The payload includes:

- `regions`: detected local regions such as `face`, `skin`, `sky`, `foliage`,
  `highlights`, `shadows`, and `foreground`.
- `operations`: recommended pixel operations such as `skin_cleanup`,
  `skin_texture_smoothing`, `face_slimming`, `sky_light_balance`,
  `landscape_dodge_burn`, and `foliage_tone_control`.
- `pixel_retouch`: endpoint and safety metadata for the separate pixel pass.

The detector currently uses local color, luma, and edge heuristics. It can later
be replaced or augmented by MediaPipe, YOLO segmentation, or SAM without
changing the response contract.

## Pixel Retouch Endpoint

```text
POST /v1/photos/pixel-retouch
```

Example JSON:

```json
{
  "batch_id": "manual-test",
  "photo_id": "IMG_0001",
  "input_path": "C:/path/to/input.jpg",
  "output_path": "C:/path/to/output.jpg",
  "scene": "portrait",
  "aesthetic": "natural",
  "operations": ["skin_cleanup", "skin_texture_smoothing", "face_slimming"],
  "strength": 0.18,
  "user_suggestion": "保持原比例，不要瘦脸，只去瑕疵"
}
```

If `operations` is empty, the service uses the operations recommended by
`local_analysis`. `user_suggestion` is optional. When present, the service passes
it to the AI planning/review prompts and applies local hard constraints such as
keeping the original ratio, skipping face slimming, and skipping skin smoothing.

## Current Safety Limits

- Face slimming is deliberately subtle and bbox-based. A landmark-based model
  should replace it before using stronger shape edits.
- Skin cleanup is conservative and aimed at small blemishes. Heavy healing or
  generative removal should remain review-gated.
- Landscape lighting uses deterministic gradient and semantic-color masks. It
  improves structure and perceived light but does not synthesize new scene
  content.
- Pixel retouch writes a new file. It does not overwrite the source image.
- User suggestions are treated as preferences plus simple hard constraints. They
  do not replace manual review for subjective portrait shape or skin decisions.

## Recommended Next Step

Add a Lightroom workflow that exports high-quality TIFF/JPG proof files, calls
`/v1/photos/pixel-retouch`, imports the returned file, and shows before/after
review in the dashboard before final export.

## Lightroom Workflow

The Lightroom plug-in now stages this as a two-step `AI Export...` workflow when
review import is enabled:

1. Export high-quality JPG sources from the currently selected Lightroom photos.
2. Call `/v1/photos/pixel-retouch` for each source, including the optional user
   suggestion from the Lightroom settings dialog.
3. Write retouched JPG files under the temp batch directory.
4. Import the retouched JPG files into Lightroom for review and select them.
5. Store a pending pixel-retouch report in plug-in preferences.
6. Run `AI Export...` again after review to copy the staged files into the final
   export directory and clear the pending report.

If review import is disabled, `AI Export...` copies the retouched files into the
final export directory in the same run.
