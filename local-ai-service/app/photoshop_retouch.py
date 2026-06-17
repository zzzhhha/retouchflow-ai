from __future__ import annotations

from pathlib import Path
from typing import Any

from .image_metrics import image_metrics
from .local_regions import analyze_local_regions, region_quality_summary
from .photoshop_bridge import create_photoshop_job, run_photoshop_job
from .photoshop_masks import attach_masks_to_operations, build_photoshop_mask_assets
from .schemas import PhotoshopJobRequest, PhotoshopRetouchRequest
from .user_intent import adjusted_pixel_strength, filter_operation_ids


PHOTOSHOP_OPERATION_ORDER = [
    "skin_cleanup",
    "skin_texture_smoothing",
    "commercial_skin_retouch",
    "face_relight",
    "face_slimming",
    "sky_light_balance",
    "landscape_dodge_burn",
    "architecture_darken",
    "foliage_green_boost",
    "foliage_tone_control",
]

PHOTOSHOP_OPERATION_TYPES = {
    "skin_cleanup": "blemish_cleanup",
    "skin_texture_smoothing": "skin_smoothing",
    "commercial_skin_retouch": "frequency_separation",
    "face_relight": "face_relight",
    "face_slimming": "face_liquify",
    "sky_light_balance": "sky_light_balance",
    "landscape_dodge_burn": "landscape_dodge_burn",
    "architecture_darken": "architecture_darken",
    "foliage_green_boost": "foliage_green_boost",
    "foliage_tone_control": "foliage_tone_control",
}


def prepare_photoshop_retouch(request: PhotoshopRetouchRequest) -> dict[str, Any]:
    source = Path(request.input_path)
    if not source.exists():
        raise FileNotFoundError(f"Input image not found: {source}")

    metrics = image_metrics(source)
    local_analysis = analyze_local_regions(
        source,
        metrics,
        request.scene,
        request.aesthetic,
        user_suggestion=request.user_suggestion,
    )
    operations_requested = _requested_operations(request.operations, local_analysis, request.user_suggestion)
    strength = _retouch_strength(request.strength, local_analysis, request.user_suggestion)
    operations_planned = _photoshop_operations(operations_requested, local_analysis, strength)
    mask_dir = _mask_dir(request.batch_id, request.photo_id or source.stem)
    mask_assets = build_photoshop_mask_assets(source, local_analysis, mask_dir)
    operations_planned = attach_masks_to_operations(operations_planned, mask_assets)

    job = create_photoshop_job(
        PhotoshopJobRequest(
            batch_id=request.batch_id,
            photo_id=request.photo_id,
            input_path=str(source),
            output_path=request.output_path,
            psd_path=request.psd_path,
            scene=request.scene,
            aesthetic=request.aesthetic,
            operations=operations_planned,
            mask_assets=mask_assets,
            strength=strength,
            user_suggestion=request.user_suggestion,
            quality_mode="commercial",
        )
    )

    if request.run:
        job = run_photoshop_job(
            job["job_id"],
            job["batch_id"],
            photoshop_exe=request.photoshop_exe or None,
            wait_seconds=request.wait_seconds,
        )

    quality: dict[str, Any] = {"before": region_quality_summary(source)}
    output_path = Path(str(job.get("output_path") or ""))
    if output_path.exists():
        quality["after"] = region_quality_summary(output_path)

    return {
        "status": str(job.get("status") or "queued"),
        "photo_id": request.photo_id,
        "input_path": str(source),
        "output_path": str(job.get("output_path") or ""),
        "psd_path": str(job.get("psd_path") or ""),
        "scene": request.scene,
        "aesthetic": request.aesthetic,
        "operations_requested": operations_requested,
        "operations_planned": operations_planned,
        "mask_assets": mask_assets,
        "local_analysis": local_analysis,
        "job": job,
        "quality": quality,
    }


def _requested_operations(
    operations: list[str],
    local_analysis: dict[str, Any],
    user_suggestion: str,
) -> list[str]:
    if operations:
        requested = [str(item).strip() for item in operations if str(item).strip()]
    else:
        requested = [str(item.get("id")) for item in local_analysis.get("operations", []) if item.get("id")]
    requested = filter_operation_ids(requested, user_suggestion)
    if "skin_texture_smoothing" in requested and "commercial_skin_retouch" not in requested:
        requested.append("commercial_skin_retouch")
    return [item for item in PHOTOSHOP_OPERATION_ORDER if item in set(requested)]


def _retouch_strength(strength: float | None, local_analysis: dict[str, Any], user_suggestion: str) -> float:
    base = strength
    if base is None:
        pixel_retouch = local_analysis.get("pixel_retouch", {}) if isinstance(local_analysis, dict) else {}
        base = float(pixel_retouch.get("safe_default_strength", 0.18))
    return round(min(max(adjusted_pixel_strength(float(base), user_suggestion), 0.03), 0.45), 3)


def _photoshop_operations(
    operation_ids: list[str],
    local_analysis: dict[str, Any],
    strength: float,
) -> list[dict[str, Any]]:
    local_operations = {
        str(item.get("id")): item
        for item in local_analysis.get("operations", [])
        if isinstance(item, dict) and item.get("id")
    }
    result: list[dict[str, Any]] = []
    for operation_id in operation_ids:
        source = local_operations.get(operation_id, {})
        result.append(
            {
                "id": operation_id,
                "type": PHOTOSHOP_OPERATION_TYPES.get(operation_id, operation_id),
                "target": source.get("target", "pixel"),
                "region_id": source.get("region_id", _default_region_id(operation_id)),
                "strength": round(float(source.get("strength", strength)) or strength, 3),
                "global_strength": strength,
                "requires_review": bool(source.get("requires_review", operation_id in {"skin_cleanup", "face_slimming"})),
                "quality_mode": "commercial",
                "photoshop_stage": _photoshop_stage(operation_id),
                "description": source.get("description", ""),
            }
        )
    return result


def _photoshop_stage(operation_id: str) -> str:
    stages = {
        "skin_cleanup": "blemish/healing",
        "skin_texture_smoothing": "skin texture smoothing",
        "commercial_skin_retouch": "frequency separation",
        "face_relight": "portrait dodge and burn",
        "face_slimming": "liquify/face-aware warp",
        "sky_light_balance": "sky tonal recovery",
        "landscape_dodge_burn": "local dodge and burn",
        "architecture_darken": "architecture exposure control",
        "foliage_green_boost": "foliage color mask",
        "foliage_tone_control": "foliage color control",
    }
    return stages.get(operation_id, "local retouch")


def _default_region_id(operation_id: str) -> str:
    if operation_id in {"skin_cleanup", "skin_texture_smoothing", "commercial_skin_retouch"}:
        return "skin"
    if operation_id in {"face_relight", "face_slimming"}:
        return "face"
    if operation_id == "sky_light_balance":
        return "sky"
    if operation_id in {"foliage_tone_control", "foliage_green_boost"}:
        return "foliage"
    if operation_id == "architecture_darken":
        return "foreground"
    return "center_subject"


def _mask_dir(batch_id: str, photo_id: str) -> Path:
    from .storage import batch_dir, safe_batch_id

    clean_photo = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(photo_id)).strip("_") or "photo"
    return batch_dir(safe_batch_id(batch_id)) / "photoshop" / "masks" / clean_photo
