from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter


MASK_REGION_IDS = {
    "subject",
    "face",
    "skin",
    "sky",
    "foliage",
    "foreground",
    "center_subject",
    "highlights",
    "shadows",
}


def build_photoshop_mask_assets(
    input_path: str | Path,
    local_analysis: dict[str, Any],
    output_dir: str | Path,
) -> list[dict[str, Any]]:
    with Image.open(input_path) as image:
        width, height = image.size
    mask_dir = Path(output_dir)
    mask_dir.mkdir(parents=True, exist_ok=True)

    assets: list[dict[str, Any]] = []
    for region in local_analysis.get("regions", []):
        if not isinstance(region, dict):
            continue
        region_id = str(region.get("id") or "")
        if region_id not in MASK_REGION_IDS:
            continue
        bbox = region.get("bbox")
        if not isinstance(bbox, dict):
            continue
        mask = _bbox_mask((width, height), bbox, _feather_for_region(region_id, width, height))
        path = mask_dir / f"{_safe_name(region_id)}.png"
        mask.save(path)
        assets.append(
            {
                "id": region_id,
                "type": region.get("type", region_id),
                "path": str(path),
                "bbox": _clean_bbox(bbox),
                "coverage": region.get("coverage", 0),
                "confidence": region.get("confidence", 0),
                "role": _mask_role(region_id),
            }
        )
    return assets


def attach_masks_to_operations(
    operations: list[dict[str, Any]],
    mask_assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(item.get("id") or ""): item for item in mask_assets}
    result = []
    for operation in operations:
        item = dict(operation)
        region_id = str(item.get("region_id") or "")
        mask = by_id.get(region_id) or _fallback_mask(item, by_id)
        if mask:
            item["mask"] = mask
            item["mask_path"] = mask.get("path", "")
            item["mask_bbox"] = mask.get("bbox", {})
        result.append(item)
    return result


def _fallback_mask(operation: dict[str, Any], masks: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    operation_id = str(operation.get("id") or operation.get("type") or "")
    if operation_id in {
        "skin_cleanup",
        "skin_texture_smoothing",
        "skin_smoothing",
        "blemish_cleanup",
        "commercial_skin_retouch",
        "frequency_separation",
    }:
        return masks.get("skin") or masks.get("face") or masks.get("subject")
    if operation_id in {"face_relight", "face_slimming", "face_warp", "face_liquify"}:
        return masks.get("face") or masks.get("subject")
    if operation_id in {"sky_light_balance", "sky_balance"}:
        return masks.get("sky")
    if operation_id in {"foliage_tone_control", "foliage_green_boost", "foliage_control"}:
        return masks.get("foliage")
    if operation_id in {"landscape_dodge_burn", "architecture_darken"}:
        return masks.get("foreground") or masks.get("center_subject") or masks.get("subject")
    return masks.get("subject")


def _bbox_mask(size: tuple[int, int], bbox: dict[str, Any], feather: int) -> Image.Image:
    width, height = size
    left = int(round(_clamp(float(bbox.get("left", 0)), 0, 1) * width))
    top = int(round(_clamp(float(bbox.get("top", 0)), 0, 1) * height))
    right = int(round(_clamp(float(bbox.get("right", 1)), 0, 1) * width))
    bottom = int(round(_clamp(float(bbox.get("bottom", 1)), 0, 1) * height))
    if right <= left:
        right = min(width, left + 1)
    if bottom <= top:
        bottom = min(height, top + 1)

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((left, top, right, bottom), fill=255)
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather))
    return mask


def _feather_for_region(region_id: str, width: int, height: int) -> int:
    base = max(width, height)
    if region_id in {"face", "skin"}:
        return max(6, int(base * 0.018))
    if region_id in {"subject", "foreground", "center_subject"}:
        return max(12, int(base * 0.035))
    return max(8, int(base * 0.025))


def _clean_bbox(bbox: dict[str, Any]) -> dict[str, float]:
    return {
        "left": round(_clamp(float(bbox.get("left", 0)), 0, 1), 4),
        "top": round(_clamp(float(bbox.get("top", 0)), 0, 1), 4),
        "right": round(_clamp(float(bbox.get("right", 1)), 0, 1), 4),
        "bottom": round(_clamp(float(bbox.get("bottom", 1)), 0, 1), 4),
    }


def _mask_role(region_id: str) -> str:
    roles = {
        "skin": "skin retouch protection mask",
        "face": "face shape and relight mask",
        "subject": "main subject mask",
        "sky": "sky tonal mask",
        "foliage": "grass and foliage mask",
        "foreground": "foreground structure mask",
        "center_subject": "center subject mask",
        "highlights": "highlight recovery mask",
        "shadows": "shadow depth mask",
    }
    return roles.get(region_id, "local adjustment mask")


def _safe_name(value: str) -> str:
    clean = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return clean.strip("_") or "mask"


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
