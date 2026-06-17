from __future__ import annotations

import colorsys
from pathlib import Path
from statistics import mean
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from .user_intent import apply_operation_intent, clean_user_suggestion, parse_user_intent


PORTRAIT_SCENES = {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}
LANDSCAPE_SCENES = {"landscape", "blue_sky", "sunset", "grass_tree", "forest", "architecture", "night"}


def analyze_local_regions(
    path: str | Path,
    metrics: dict[str, Any],
    scene: str,
    aesthetic: str,
    user_suggestion: str = "",
) -> dict[str, Any]:
    """Build semantic region and pixel-retouch plans from a preview image.

    The analyzer is intentionally dependency-light. It uses deterministic color,
    luma, and edge masks as a first stage, and can be replaced later by
    MediaPipe/SAM/YOLO without changing the response shape.
    """

    image = _open_preview(path)
    sample = _sample_pixels(image)
    regions = _regions_from_sample(sample, image.width, image.height, metrics, scene)
    operations = _operations_for_regions(regions, metrics, scene, aesthetic)
    operations = apply_operation_intent(operations, user_suggestion, regions, scene)
    return {
        "source": "local_color_luma_rules",
        "user_suggestion": clean_user_suggestion(user_suggestion),
        "user_intent": parse_user_intent(user_suggestion),
        "image_size": {"width": image.width, "height": image.height},
        "regions": regions,
        "operations": operations,
        "pixel_retouch": {
            "available": bool(operations),
            "requires_render_export": True,
            "safe_default_strength": _safe_default_strength(scene, metrics),
            "endpoint": "/v1/photos/pixel-retouch",
        },
    }


def _open_preview(path: str | Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image.thumbnail((512, 512))
    return image


def _sample_pixels(image: Image.Image) -> list[dict[str, float | int | tuple[int, int, int]]]:
    pixels: list[dict[str, float | int | tuple[int, int, int]]] = []
    width, height = image.size
    data = list(image.getdata())
    for index, (red, green, blue) in enumerate(data):
        x = index % width
        y = index // width
        hue, sat, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        luma = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        pixels.append(
            {
                "x": x,
                "y": y,
                "rgb": (red, green, blue),
                "hue": hue * 360,
                "sat": sat,
                "value": value,
                "luma": luma,
            }
        )
    return pixels


def _regions_from_sample(
    pixels: list[dict[str, float | int | tuple[int, int, int]]],
    width: int,
    height: int,
    metrics: dict[str, Any],
    scene: str,
) -> list[dict[str, Any]]:
    total = max(len(pixels), 1)
    regions: list[dict[str, Any]] = []

    skin_points = [
        point
        for point in pixels
        if _is_skin_like(point) and float(point["y"]) < height * 0.92
    ]
    skin_region = _region_from_points(
        "skin",
        "skin",
        skin_points,
        total,
        width,
        height,
        min_coverage=0.018 if scene in PORTRAIT_SCENES else 0.045,
    )
    if skin_region:
        skin_region["confidence"] = _confidence(float(skin_region["coverage"]) * 6.0 + float(metrics.get("skin_tone_ratio", 0)))
        regions.append(skin_region)
        if scene in PORTRAIT_SCENES or float(metrics.get("skin_tone_ratio", 0)) >= 0.08:
            face = dict(skin_region)
            face["id"] = "face"
            face["type"] = "face"
            face["confidence"] = _confidence(float(face["confidence"]) + 0.15)
            regions.append(face)

    sky_points = [
        point
        for point in pixels
        if _is_sky_like(point) and float(point["y"]) < height * 0.72
    ]
    sky_region = _region_from_points("sky", "sky", sky_points, total, width, height, min_coverage=0.025)
    if sky_region:
        sky_region["confidence"] = _confidence(float(sky_region["coverage"]) * 4.5 + float(metrics.get("blue_ratio", 0)))
        regions.append(sky_region)

    foliage_points = [point for point in pixels if _is_foliage_like(point)]
    foliage_region = _region_from_points("foliage", "foliage", foliage_points, total, width, height, min_coverage=0.035)
    if foliage_region:
        foliage_region["confidence"] = _confidence(float(foliage_region["coverage"]) * 3.0 + float(metrics.get("green_ratio", 0)))
        regions.append(foliage_region)

    bright_points = [point for point in pixels if float(point["luma"]) >= 205]
    bright_region = _region_from_points("highlights", "luma", bright_points, total, width, height, min_coverage=0.035)
    if bright_region:
        bright_region["confidence"] = _confidence(float(metrics.get("bright_ratio", 0)) * 4.0)
        regions.append(bright_region)

    dark_points = [point for point in pixels if float(point["luma"]) <= 62]
    dark_region = _region_from_points("shadows", "luma", dark_points, total, width, height, min_coverage=0.035)
    if dark_region:
        dark_region["confidence"] = _confidence(float(metrics.get("dark_ratio", 0)) * 4.0)
        regions.append(dark_region)

    subject_region = _subject_region(regions, width, height, scene)
    if subject_region:
        regions.insert(0, subject_region)

    return regions


def _region_from_points(
    region_id: str,
    region_type: str,
    points: list[dict[str, float | int | tuple[int, int, int]]],
    total_count: int,
    width: int,
    height: int,
    min_coverage: float,
) -> dict[str, Any] | None:
    coverage = len(points) / max(total_count, 1)
    if coverage < min_coverage:
        return None

    xs = [int(point["x"]) for point in points]
    ys = [int(point["y"]) for point in points]
    bbox = {
        "left": round(min(xs) / max(width - 1, 1), 4),
        "top": round(min(ys) / max(height - 1, 1), 4),
        "right": round(max(xs) / max(width - 1, 1), 4),
        "bottom": round(max(ys) / max(height - 1, 1), 4),
    }
    return {
        "id": region_id,
        "type": region_type,
        "coverage": round(coverage, 4),
        "bbox": bbox,
        "confidence": _confidence(coverage * 4.0),
    }


def _subject_region(regions: list[dict[str, Any]], width: int, height: int, scene: str) -> dict[str, Any] | None:
    face = _find_region(regions, "face")
    if face:
        return {
            "id": "subject",
            "type": "subject",
            "coverage": min(0.75, round(float(face["coverage"]) * 2.4, 4)),
            "bbox": _expand_bbox(face["bbox"], 0.2, 0.28),
            "confidence": _confidence(float(face["confidence"]) + 0.08),
        }

    sky = _find_region(regions, "sky")
    if sky and scene in LANDSCAPE_SCENES:
        top = min(0.9, float(sky["bbox"].get("bottom", 0.45)) + 0.02)
        return {
            "id": "foreground",
            "type": "subject",
            "coverage": round(max(0.1, 1.0 - top), 4),
            "bbox": {"left": 0, "top": round(top, 4), "right": 1, "bottom": 1},
            "confidence": 0.62,
        }

    if scene in LANDSCAPE_SCENES:
        return {
            "id": "center_subject",
            "type": "subject",
            "coverage": 0.36,
            "bbox": {"left": 0.18, "top": 0.2, "right": 0.82, "bottom": 0.84},
            "confidence": 0.38,
        }
    return None


def _operations_for_regions(
    regions: list[dict[str, Any]],
    metrics: dict[str, Any],
    scene: str,
    aesthetic: str,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    has_face = _find_region(regions, "face") is not None
    has_skin = _find_region(regions, "skin") is not None
    has_sky = _find_region(regions, "sky") is not None
    has_foliage = _find_region(regions, "foliage") is not None

    if scene in PORTRAIT_SCENES or has_face:
        if has_skin:
            operations.append(
                _operation(
                    "skin_cleanup",
                    "pixel",
                    "skin",
                    "Remove small blemishes inside the skin region with conservative healing.",
                    0.22,
                    requires_review=True,
                )
            )
            operations.append(
                _operation(
                    "skin_texture_smoothing",
                    "pixel",
                    "skin",
                    "Smooth uneven skin tone while preserving edges and facial detail.",
                    0.18 if aesthetic in {"texture", "master"} else 0.28,
                    requires_review=True,
                )
            )
        if has_face:
            operations.append(
                _operation(
                    "face_slimming",
                    "pixel",
                    "face",
                    "Apply a subtle face-shape warp; limited strength avoids background distortion.",
                    0.08,
                    requires_review=True,
                )
            )
            if float(metrics.get("dark_ratio", 0)) > 0.18 or float(metrics.get("avg_luma", 128)) < 120:
                operations.append(
                    _operation(
                        "face_relight",
                        "pixel",
                        "face",
                        "Lift facial midtones and soften harsh shadow transitions.",
                        0.18,
                        requires_review=False,
                    )
                )

    if scene in LANDSCAPE_SCENES or has_sky or has_foliage:
        if has_sky:
            operations.append(
                _operation(
                    "sky_light_balance",
                    "pixel",
                    "sky",
                    "Recover sky highlights and add gentle tonal separation.",
                    0.22,
                    requires_review=False,
                )
            )
        operations.append(
            _operation(
                "landscape_dodge_burn",
                "pixel",
                "foreground" if _find_region(regions, "foreground") else "center_subject",
                "Add restrained local light and shadow depth for landscape structure.",
                0.2,
                requires_review=False,
            )
        )
        if has_foliage:
            operations.append(
                _operation(
                    "foliage_tone_control",
                    "pixel",
                    "foliage",
                    "Reduce harsh green/yellow saturation and add foliage separation.",
                    0.18,
                    requires_review=False,
                )
            )

    return operations


def _operation(
    operation_id: str,
    target: str,
    region_id: str,
    description: str,
    strength: float,
    requires_review: bool,
) -> dict[str, Any]:
    return {
        "id": operation_id,
        "target": target,
        "region_id": region_id,
        "status": "ready_for_pixel_endpoint",
        "strength": round(strength, 3),
        "requires_review": requires_review,
        "description": description,
    }


def _is_skin_like(point: dict[str, float | int | tuple[int, int, int]]) -> bool:
    red, green, blue = point["rgb"]  # type: ignore[misc]
    hue = float(point["hue"])
    sat = float(point["sat"])
    value = float(point["value"])
    return value > 0.22 and 7 <= hue <= 52 and 0.12 <= sat <= 0.72 and int(red) > int(blue)


def _is_sky_like(point: dict[str, float | int | tuple[int, int, int]]) -> bool:
    hue = float(point["hue"])
    sat = float(point["sat"])
    value = float(point["value"])
    return value > 0.25 and sat > 0.12 and 178 <= hue <= 258


def _is_foliage_like(point: dict[str, float | int | tuple[int, int, int]]) -> bool:
    hue = float(point["hue"])
    sat = float(point["sat"])
    value = float(point["value"])
    return value > 0.18 and sat > 0.16 and 68 <= hue <= 172


def _find_region(regions: list[dict[str, Any]], region_id: str) -> dict[str, Any] | None:
    for region in regions:
        if region.get("id") == region_id:
            return region
    return None


def _expand_bbox(bbox: dict[str, Any], x_margin: float, y_margin: float) -> dict[str, float]:
    left = float(bbox.get("left", 0))
    top = float(bbox.get("top", 0))
    right = float(bbox.get("right", 1))
    bottom = float(bbox.get("bottom", 1))
    width = max(0.01, right - left)
    height = max(0.01, bottom - top)
    return {
        "left": round(max(0.0, left - width * x_margin), 4),
        "top": round(max(0.0, top - height * y_margin), 4),
        "right": round(min(1.0, right + width * x_margin), 4),
        "bottom": round(min(1.0, bottom + height * y_margin), 4),
    }


def _safe_default_strength(scene: str, metrics: dict[str, Any]) -> float:
    if scene in PORTRAIT_SCENES:
        sharpness = float(metrics.get("sharpness", 18))
        return 0.18 if sharpness > 18 else 0.24
    if scene in LANDSCAPE_SCENES:
        return 0.2
    return 0.16


def _confidence(value: float) -> float:
    return round(min(max(value, 0.05), 0.98), 3)


def region_quality_summary(path: str | Path) -> dict[str, float]:
    """Return simple edge and luma stats for debugging pixel-retouch output."""

    image = _open_preview(path)
    gray = image.convert("L")
    edge = gray.filter(ImageFilter.FIND_EDGES)
    return {
        "avg_luma": round(mean(list(gray.getdata())), 2),
        "edge_mean": round(ImageStat.Stat(edge).mean[0], 2),
        "luma_stddev": round(ImageStat.Stat(gray).stddev[0], 2),
    }
