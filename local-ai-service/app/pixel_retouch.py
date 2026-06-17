from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter

from .image_metrics import image_metrics
from .local_regions import analyze_local_regions, region_quality_summary
from .user_intent import adjusted_pixel_strength, filter_operation_ids


DEFAULT_OPERATION_ORDER = [
    "skin_cleanup",
    "skin_texture_smoothing",
    "face_relight",
    "face_slimming",
    "sky_light_balance",
    "landscape_dodge_burn",
    "architecture_darken",
    "foliage_green_boost",
    "foliage_tone_control",
]


def render_pixel_retouch(
    input_path: str | Path,
    output_path: str | Path,
    scene: str = "auto",
    aesthetic: str = "natural",
    operations: list[str] | None = None,
    strength: float | None = None,
    user_suggestion: str = "",
) -> dict[str, Any]:
    source = Path(input_path)
    target = Path(output_path)
    if source.resolve() == target.resolve():
        raise ValueError("output_path must be different from input_path")
    if not source.exists():
        raise FileNotFoundError(f"Input image not found: {source}")

    metrics = image_metrics(source)
    local_analysis = analyze_local_regions(source, metrics, scene, aesthetic, user_suggestion=user_suggestion)
    requested = _requested_operations(operations, local_analysis, user_suggestion)
    base_strength = strength if strength is not None else local_analysis["pixel_retouch"]["safe_default_strength"]
    global_strength = _clamp(adjusted_pixel_strength(base_strength, user_suggestion), 0.03, 0.45)

    image = Image.open(source).convert("RGB")
    applied: list[dict[str, Any]] = []
    for operation_id in DEFAULT_OPERATION_ORDER:
        if operation_id not in requested:
            continue
        before = image
        image, detail = _apply_operation(image, operation_id, local_analysis, global_strength)
        if image is not before:
            applied.append(detail)

    target.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict[str, Any] = {}
    if target.suffix.lower() in {".jpg", ".jpeg"}:
        save_kwargs.update({"quality": 94, "subsampling": 1})
    image.save(target, **save_kwargs)

    return {
        "status": "ok",
        "input_path": str(source),
        "output_path": str(target),
        "scene": scene,
        "aesthetic": aesthetic,
        "operations_requested": requested,
        "operations_applied": applied,
        "local_analysis": local_analysis,
        "quality": {
            "before": region_quality_summary(source),
            "after": region_quality_summary(target),
        },
    }


def _requested_operations(operations: list[str] | None, local_analysis: dict[str, Any], user_suggestion: str) -> list[str]:
    if operations:
        requested = [str(item).strip() for item in operations if str(item).strip()]
    else:
        requested = [str(item.get("id")) for item in local_analysis.get("operations", []) if item.get("id")]
    requested = filter_operation_ids(requested, user_suggestion)
    return [item for item in DEFAULT_OPERATION_ORDER if item in set(requested)]


def _apply_operation(
    image: Image.Image,
    operation_id: str,
    local_analysis: dict[str, Any],
    strength: float,
) -> tuple[Image.Image, dict[str, Any]]:
    if operation_id in {"skin_cleanup", "skin_texture_smoothing"}:
        return _skin_blend(image, operation_id, strength)
    if operation_id == "face_relight":
        return _bbox_brightness(image, "face", local_analysis, 1.0 + strength * 0.5, operation_id)
    if operation_id == "face_slimming":
        return _face_slim(image, local_analysis, strength)
    if operation_id == "sky_light_balance":
        return _sky_balance(image, strength)
    if operation_id == "landscape_dodge_burn":
        return _landscape_light(image, strength)
    if operation_id == "architecture_darken":
        return _architecture_darken(image, local_analysis, strength)
    if operation_id == "foliage_green_boost":
        return _foliage_green_boost(image, strength)
    if operation_id == "foliage_tone_control":
        return _foliage_control(image, strength)
    return image, {"id": operation_id, "status": "skipped", "reason": "unknown operation"}


def _skin_blend(image: Image.Image, operation_id: str, strength: float) -> tuple[Image.Image, dict[str, Any]]:
    mask = _skin_mask(image)
    if _mask_coverage(mask) < 0.01:
        return image, {"id": operation_id, "status": "skipped", "reason": "skin mask too small"}

    if operation_id == "skin_cleanup":
        treated = image.filter(ImageFilter.MedianFilter(3))
        opacity = _mask_opacity(mask, strength * 0.58)
    else:
        soft = image.filter(ImageFilter.GaussianBlur(radius=1.2 + strength * 2.0))
        detail = image.filter(ImageFilter.UnsharpMask(radius=1.0, percent=45, threshold=4))
        treated = Image.blend(soft, detail, 0.26)
        opacity = _mask_opacity(mask, strength * 0.7)
    return Image.composite(treated, image, opacity), {
        "id": operation_id,
        "status": "applied",
        "mask": "skin",
        "strength": round(strength, 3),
    }


def _bbox_brightness(
    image: Image.Image,
    region_id: str,
    local_analysis: dict[str, Any],
    factor: float,
    operation_id: str,
) -> tuple[Image.Image, dict[str, Any]]:
    bbox = _region_bbox(local_analysis, region_id)
    if bbox is None:
        return image, {"id": operation_id, "status": "skipped", "reason": f"{region_id} region missing"}
    box = _absolute_box(bbox, image.size)
    if _empty_box(box):
        return image, {"id": operation_id, "status": "skipped", "reason": "empty region"}
    layer = image.copy()
    crop = layer.crop(box)
    crop = ImageEnhance.Brightness(crop).enhance(factor)
    mask = _feather_mask(crop.size, 0.16)
    layer.paste(crop, box, mask)
    return layer, {"id": operation_id, "status": "applied", "mask": region_id, "factor": round(factor, 3)}


def _face_slim(image: Image.Image, local_analysis: dict[str, Any], strength: float) -> tuple[Image.Image, dict[str, Any]]:
    bbox = _region_bbox(local_analysis, "face")
    if bbox is None:
        return image, {"id": "face_slimming", "status": "skipped", "reason": "face region missing"}
    box = _absolute_box(_expand_bbox(bbox, 0.1, 0.08), image.size)
    if _empty_box(box):
        return image, {"id": "face_slimming", "status": "skipped", "reason": "empty face region"}

    crop = image.crop(box)
    width, height = crop.size
    shrink = _clamp(strength * 0.45, 0.012, 0.12)
    new_width = max(2, int(round(width * (1.0 - shrink))))
    if new_width >= width:
        return image, {"id": "face_slimming", "status": "skipped", "reason": "strength too low"}

    slim = crop.resize((new_width, height), Image.Resampling.BICUBIC)
    result = image.copy()
    x0, y0, _, _ = box
    paste_x = x0 + (width - new_width) // 2
    mask = _feather_mask(slim.size, 0.22)
    result.paste(slim, (paste_x, y0), mask)
    return result, {
        "id": "face_slimming",
        "status": "applied",
        "mask": "face",
        "width_shrink_ratio": round(shrink, 4),
    }


def _sky_balance(image: Image.Image, strength: float) -> tuple[Image.Image, dict[str, Any]]:
    mask = _sky_mask(image)
    if _mask_coverage(mask) < 0.015:
        return image, {"id": "sky_light_balance", "status": "skipped", "reason": "sky mask too small"}
    cooler = ImageEnhance.Color(image).enhance(1.0 + strength * 0.25)
    cooler = ImageEnhance.Contrast(cooler).enhance(1.0 + strength * 0.18)
    cooler = ImageEnhance.Brightness(cooler).enhance(1.0 - strength * 0.08)
    return Image.composite(cooler, image, _mask_opacity(mask, 0.76)), {
        "id": "sky_light_balance",
        "status": "applied",
        "mask": "sky",
        "strength": round(strength, 3),
    }


def _landscape_light(image: Image.Image, strength: float) -> tuple[Image.Image, dict[str, Any]]:
    width, height = image.size
    mask_size = _work_size(image.size, 900)
    mask_width, mask_height = mask_size
    light_mask = Image.new("L", mask_size, 0)
    center_x = mask_width * 0.42
    center_y = mask_height * 0.36
    max_distance = max(mask_width, mask_height) * 0.85
    pixels = light_mask.load()
    for y in range(mask_height):
        for x in range(mask_width):
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            value = max(0.0, 1.0 - distance / max_distance)
            if y > mask_height * 0.58:
                value *= 0.72
            pixels[x, y] = int(255 * (value**1.9))
    if mask_size != image.size:
        light_mask = light_mask.resize(image.size, _resample_filter())
    bright = ImageEnhance.Brightness(image).enhance(1.0 + strength * 0.28)
    contrast = ImageEnhance.Contrast(bright).enhance(1.0 + strength * 0.18)
    return Image.composite(contrast, image, _mask_opacity(light_mask.filter(ImageFilter.GaussianBlur(18)), 0.58)), {
        "id": "landscape_dodge_burn",
        "status": "applied",
        "mask": "radial_light",
        "strength": round(strength, 3),
    }


def _foliage_control(image: Image.Image, strength: float) -> tuple[Image.Image, dict[str, Any]]:
    mask = _foliage_mask(image)
    if _mask_coverage(mask) < 0.015:
        return image, {"id": "foliage_tone_control", "status": "skipped", "reason": "foliage mask too small"}
    controlled = ImageEnhance.Color(image).enhance(1.0 - strength * 0.32)
    controlled = ImageEnhance.Contrast(controlled).enhance(1.0 + strength * 0.14)
    return Image.composite(controlled, image, _mask_opacity(mask, 0.7)), {
        "id": "foliage_tone_control",
        "status": "applied",
        "mask": "foliage",
        "strength": round(strength, 3),
    }


def _architecture_darken(image: Image.Image, local_analysis: dict[str, Any], strength: float) -> tuple[Image.Image, dict[str, Any]]:
    region_id = _first_region_id(local_analysis, ["foreground", "center_subject", "shadows", "subject"])
    if not region_id:
        return image, {"id": "architecture_darken", "status": "skipped", "reason": "architecture/foreground region missing"}
    bbox = _region_bbox(local_analysis, region_id)
    if bbox is None:
        return image, {"id": "architecture_darken", "status": "skipped", "reason": f"{region_id} region missing"}
    box = _absolute_box(bbox, image.size)
    if _empty_box(box):
        return image, {"id": "architecture_darken", "status": "skipped", "reason": "empty region"}

    layer = image.copy()
    crop = layer.crop(box)
    crop = ImageEnhance.Brightness(crop).enhance(1.0 - strength * 0.34)
    crop = ImageEnhance.Contrast(crop).enhance(1.0 + strength * 0.12)
    mask = _feather_mask(crop.size, 0.2)
    layer.paste(crop, box, mask)
    return layer, {
        "id": "architecture_darken",
        "status": "applied",
        "mask": region_id,
        "strength": round(strength, 3),
    }


def _foliage_green_boost(image: Image.Image, strength: float) -> tuple[Image.Image, dict[str, Any]]:
    mask = _foliage_mask(image)
    if _mask_coverage(mask) < 0.015:
        return image, {"id": "foliage_green_boost", "status": "skipped", "reason": "foliage mask too small"}
    greener = ImageEnhance.Color(image).enhance(1.0 + strength * 0.42)
    greener = ImageEnhance.Brightness(greener).enhance(1.0 + strength * 0.08)
    greener = ImageEnhance.Contrast(greener).enhance(1.0 + strength * 0.08)
    return Image.composite(greener, image, _mask_opacity(mask, 0.7)), {
        "id": "foliage_green_boost",
        "status": "applied",
        "mask": "foliage",
        "strength": round(strength, 3),
    }


def _skin_mask(image: Image.Image) -> Image.Image:
    return _color_mask(image, lambda r, g, b, h, s, v: v > 0.22 and 7 <= h <= 52 and 0.12 <= s <= 0.72 and r > b)


def _sky_mask(image: Image.Image) -> Image.Image:
    width, height = image.size
    return _color_mask(
        image,
        lambda r, g, b, h, s, v, y_factor=0: v > 0.25 and s > 0.12 and 178 <= h <= 258,
        max_y=int(height * 0.76),
    )


def _foliage_mask(image: Image.Image) -> Image.Image:
    return _color_mask(image, lambda r, g, b, h, s, v: v > 0.18 and s > 0.16 and 68 <= h <= 172)


def _color_mask(image: Image.Image, predicate: Any, max_y: int | None = None) -> Image.Image:
    source_size = image.size
    work = image
    if max(source_size) > 1024:
        work = image.resize(_work_size(source_size, 1024), _resample_filter())
    width, height = work.size
    mask = Image.new("L", work.size, 0)
    src = work.load()
    out = mask.load()
    scaled_max_y = None if max_y is None else int(round(max_y * height / max(source_size[1], 1)))
    y_limit = height if scaled_max_y is None else max(0, min(height, scaled_max_y))
    for y in range(y_limit):
        for x in range(width):
            red, green, blue = src[x, y]
            hue, sat, value = _hsv(red, green, blue)
            if predicate(red, green, blue, hue, sat, value):
                out[x, y] = 255
    if work.size != source_size:
        mask = mask.resize(source_size, _resample_filter())
    return mask.filter(ImageFilter.GaussianBlur(1.2))


def _work_size(size: tuple[int, int], max_edge: int) -> tuple[int, int]:
    width, height = size
    longest = max(width, height)
    if longest <= max_edge:
        return size
    scale = max_edge / longest
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def _resample_filter() -> Any:
    return getattr(Image, "Resampling", Image).BILINEAR


def _hsv(red: int, green: int, blue: int) -> tuple[float, float, float]:
    import colorsys

    hue, sat, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
    return hue * 360, sat, value


def _region_bbox(local_analysis: dict[str, Any], region_id: str) -> dict[str, Any] | None:
    for region in local_analysis.get("regions", []):
        if region.get("id") == region_id and isinstance(region.get("bbox"), dict):
            return region["bbox"]
    return None


def _first_region_id(local_analysis: dict[str, Any], region_ids: list[str]) -> str:
    available = {str(region.get("id") or "") for region in local_analysis.get("regions", []) if isinstance(region, dict)}
    for region_id in region_ids:
        if region_id in available:
            return region_id
    return ""


def _absolute_box(bbox: dict[str, Any], size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    left = int(round(_clamp(float(bbox.get("left", 0)), 0, 1) * width))
    top = int(round(_clamp(float(bbox.get("top", 0)), 0, 1) * height))
    right = int(round(_clamp(float(bbox.get("right", 1)), 0, 1) * width))
    bottom = int(round(_clamp(float(bbox.get("bottom", 1)), 0, 1) * height))
    return left, top, right, bottom


def _expand_bbox(bbox: dict[str, Any], x_margin: float, y_margin: float) -> dict[str, float]:
    left = float(bbox.get("left", 0))
    top = float(bbox.get("top", 0))
    right = float(bbox.get("right", 1))
    bottom = float(bbox.get("bottom", 1))
    width = max(0.01, right - left)
    height = max(0.01, bottom - top)
    return {
        "left": max(0.0, left - width * x_margin),
        "top": max(0.0, top - height * y_margin),
        "right": min(1.0, right + width * x_margin),
        "bottom": min(1.0, bottom + height * y_margin),
    }


def _empty_box(box: tuple[int, int, int, int]) -> bool:
    left, top, right, bottom = box
    return right - left < 4 or bottom - top < 4


def _feather_mask(size: tuple[int, int], margin_ratio: float) -> Image.Image:
    width, height = size
    mask = Image.new("L", size, 255)
    pixels = mask.load()
    margin_x = max(1, int(width * margin_ratio))
    margin_y = max(1, int(height * margin_ratio))
    for y in range(height):
        for x in range(width):
            dx = min(x / margin_x, (width - 1 - x) / margin_x, 1.0)
            dy = min(y / margin_y, (height - 1 - y) / margin_y, 1.0)
            pixels[x, y] = int(255 * max(0.0, min(dx, dy)))
    return mask.filter(ImageFilter.GaussianBlur(max(1, int(min(width, height) * 0.015))))


def _mask_opacity(mask: Image.Image, opacity: float) -> Image.Image:
    opacity = _clamp(opacity, 0.0, 1.0)
    return mask.point(lambda value: int(value * opacity))


def _mask_coverage(mask: Image.Image) -> float:
    values = mask.getdata()
    return sum(1 for value in values if value > 12) / max(mask.width * mask.height, 1)


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(float(value), low), high)
