from __future__ import annotations

from typing import Any

from .user_intent import parse_user_intent


EXECUTE_LEVEL = "basic_plus_advanced_execute"
PORTRAIT_SCENES = {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}
SOFT_VIGNETTE_SCENES = {"sunset", "night", "blue_sky"}


def build_advanced_plan(
    metrics: dict[str, Any],
    scene: str,
    aesthetic: str,
    edit_level: str,
    crop_suggestion: dict[str, Any],
    local_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    applied = edit_level == EXECUTE_LEVEL
    settings: dict[str, Any] = {}
    sections: list[dict[str, Any]] = []

    hsl = color_mixer_settings(scene, aesthetic, metrics)
    if hsl:
        sections.append({"name": "混色器", "applied": applied, "settings": hsl})
        if applied:
            settings.update(hsl)

    foliage = foliage_green_lightroom_settings(_user_intent(local_analysis or {}))
    if foliage:
        sections.append({"name": "草地/绿植增强", "applied": applied, "settings": foliage})
        if applied:
            settings.update(foliage)

    curve = tone_curve_settings(scene, aesthetic)
    if curve:
        sections.append({"name": "曲线", "applied": applied, "settings": curve})
        if applied:
            settings.update(curve)

    grading = color_grading_settings(scene, aesthetic)
    if grading:
        sections.append({"name": "色彩分级", "applied": applied, "settings": grading})
        if applied:
            settings.update(grading)

    vignette = vignette_lightroom_settings(_user_intent(local_analysis or {}), scene, aesthetic)
    if vignette:
        sections.append({"name": "暗角/主体突出", "applied": applied, "settings": vignette})
        if applied:
            settings.update(vignette)

    crop = crop_lightroom_settings(crop_suggestion)
    if crop:
        sections.append({"name": "裁剪/重构图", "applied": applied, "settings": crop})
        if applied:
            settings.update(crop)

    mask_plan = mask_execution_plan(scene, aesthetic, metrics)
    if mask_plan:
        sections.append({"name": "蒙版", "applied": False, "settings": {}, "notes": mask_plan})

    sections.extend(local_region_sections(local_analysis or {}))

    return {
        "applied": applied,
        "lightroom_settings": settings,
        "sections": sections,
        "limitations": [
            "Lightroom Classic SDK 没有稳定公开接口可直接创建 AI 蒙版；蒙版当前保留为进阶计划，后续应走外部 TIFF 精修链路。"
        ],
    }


def local_region_sections(local_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    regions = local_analysis.get("regions")
    operations = local_analysis.get("operations")
    if not isinstance(regions, list) or not isinstance(operations, list):
        return []

    region_notes: list[str] = []
    for region in regions[:8]:
        if not isinstance(region, dict):
            continue
        region_notes.append(
            "id={id}; type={type}; coverage={coverage}; confidence={confidence}; bbox={bbox}".format(
                id=region.get("id", ""),
                type=region.get("type", ""),
                coverage=region.get("coverage", 0),
                confidence=region.get("confidence", 0),
                bbox=region.get("bbox", {}),
            )
        )

    operation_notes: list[str] = []
    for operation in operations[:8]:
        if not isinstance(operation, dict):
            continue
        operation_notes.append(
            "id={id}; region={region}; strength={strength}; status={status}".format(
                id=operation.get("id", ""),
                region=operation.get("region_id", ""),
                strength=operation.get("strength", 0),
                status=operation.get("status", ""),
            )
        )

    return [
        {
            "name": "local_region_analysis",
            "applied": False,
            "settings": {},
            "notes": region_notes or ["No local regions detected."],
        },
        {
            "name": "pixel_retouch_plan",
            "applied": False,
            "settings": {},
            "notes": operation_notes or ["No pixel retouch operations recommended."],
        },
    ]


def _user_intent(local_analysis: dict[str, Any]) -> dict[str, bool]:
    intent = local_analysis.get("user_intent")
    if isinstance(intent, dict):
        return {str(key): bool(value) for key, value in intent.items()}
    return parse_user_intent(local_analysis.get("user_suggestion", ""))


def vignette_lightroom_settings(intent: dict[str, Any], scene: str, aesthetic: str = "natural") -> dict[str, int]:
    wants_vignette = bool(intent.get("vignette")) or bool(intent.get("subject_focus"))
    if not wants_vignette or intent.get("avoid_vignette"):
        return {}

    explicit = bool(intent.get("vignette"))
    amount = -20 if explicit else -12
    if scene in PORTRAIT_SCENES:
        amount -= 3 if explicit else 0
    if scene in SOFT_VIGNETTE_SCENES:
        amount += 6
    if aesthetic in {"sweet", "japanese_clear", "warm_soft"}:
        amount += 3
    if intent.get("natural"):
        amount += 4

    return {
        "PostCropVignetteAmount": int(_clamp(amount, -28, -8)),
        "PostCropVignetteMidpoint": 44 if scene in PORTRAIT_SCENES else 50,
        "PostCropVignetteFeather": 78,
        "PostCropVignetteRoundness": 0,
        "PostCropVignetteStyle": 1,
    }


def foliage_green_lightroom_settings(intent: dict[str, Any]) -> dict[str, int]:
    if not intent.get("foliage_green_boost") or intent.get("avoid_foliage_green_boost"):
        return {}
    return {
        "SaturationAdjustmentGreen": 12,
        "LuminanceAdjustmentGreen": 6,
        "HueAdjustmentGreen": -4,
        "SaturationAdjustmentYellow": 4,
    }


def color_mixer_settings(scene: str, aesthetic: str, metrics: dict[str, Any]) -> dict[str, int]:
    settings: dict[str, int] = {}

    if scene in {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}:
        _add(settings, "Saturation", "Red", -4)
        _add(settings, "Saturation", "Orange", -4)
        _add(settings, "Luminance", "Orange", 6)
        _add(settings, "Saturation", "Yellow", -5)
        _add(settings, "Saturation", "Green", -10)
    elif scene in {"grass_tree", "forest"}:
        _add(settings, "Hue", "Green", -8)
        _add(settings, "Saturation", "Green", -18)
        _add(settings, "Saturation", "Yellow", -8)
        _add(settings, "Luminance", "Green", 8)
        _add(settings, "Luminance", "Yellow", 4)
    elif scene in {"landscape", "blue_sky"}:
        _add(settings, "Saturation", "Blue", 10)
        _add(settings, "Saturation", "Aqua", 6)
        _add(settings, "Luminance", "Blue", -6)
        _add(settings, "Saturation", "Green", -4)
        _add(settings, "Saturation", "Yellow", -4)
    elif scene == "sunset":
        _add(settings, "Saturation", "Red", 8)
        _add(settings, "Saturation", "Orange", 12)
        _add(settings, "Saturation", "Yellow", 8)
        _add(settings, "Saturation", "Blue", -8)
    elif scene == "flower":
        _add(settings, "Saturation", "Red", 8)
        _add(settings, "Saturation", "Magenta", 10)
        _add(settings, "Saturation", "Purple", 6)
        _add(settings, "Luminance", "Red", 5)
        _add(settings, "Saturation", "Green", -10)
    elif scene == "night":
        _add(settings, "Saturation", "Yellow", -8)
        _add(settings, "Saturation", "Orange", -6)
        _add(settings, "Saturation", "Blue", 6)
        _add(settings, "Luminance", "Blue", -6)
    elif scene == "food":
        _add(settings, "Saturation", "Orange", 10)
        _add(settings, "Saturation", "Yellow", 8)
        _add(settings, "Luminance", "Orange", 8)
        _add(settings, "Saturation", "Green", -6)

    if aesthetic == "sweet":
        _add(settings, "Saturation", "Red", -4)
        _add(settings, "Saturation", "Orange", -5)
        _add(settings, "Luminance", "Orange", 8)
    elif aesthetic in {"texture", "master", "high_gray"}:
        _add(settings, "Saturation", "Orange", -2)
        _add(settings, "Saturation", "Yellow", -5)
        _add(settings, "Saturation", "Green", -6)
        _add(settings, "Luminance", "Orange", 3)
    elif aesthetic == "film":
        _add(settings, "Hue", "Green", -5)
        _add(settings, "Saturation", "Green", -8)
        _add(settings, "Saturation", "Blue", -6)
    elif aesthetic == "cool_transparent":
        _add(settings, "Saturation", "Aqua", 8)
        _add(settings, "Saturation", "Blue", 8)
        _add(settings, "Luminance", "Blue", 6)

    if float(metrics.get("avg_saturation", 45)) > 70:
        for color in ("Red", "Orange", "Yellow", "Green", "Aqua", "Blue", "Purple", "Magenta"):
            _add(settings, "Saturation", color, -3)

    return _clamp_settings(settings, -30, 30)


def tone_curve_settings(scene: str, aesthetic: str) -> dict[str, int]:
    if aesthetic in {"texture", "master"} or scene in {"landscape", "architecture", "forest"}:
        return {
            "ParametricShadows": -6,
            "ParametricDarks": -4,
            "ParametricLights": 6,
            "ParametricHighlights": 8,
            "ParametricShadowSplit": 25,
            "ParametricMidtoneSplit": 50,
            "ParametricHighlightSplit": 75,
        }
    if aesthetic in {"sweet", "japanese_clear", "warm_soft"}:
        return {
            "ParametricShadows": 6,
            "ParametricDarks": 4,
            "ParametricLights": 2,
            "ParametricHighlights": -5,
            "ParametricShadowSplit": 25,
            "ParametricMidtoneSplit": 50,
            "ParametricHighlightSplit": 75,
        }
    if aesthetic == "high_gray":
        return {
            "ParametricShadows": 10,
            "ParametricDarks": 6,
            "ParametricLights": -4,
            "ParametricHighlights": -8,
            "ParametricShadowSplit": 25,
            "ParametricMidtoneSplit": 50,
            "ParametricHighlightSplit": 75,
        }
    if aesthetic == "film":
        return {
            "ParametricShadows": 5,
            "ParametricDarks": 2,
            "ParametricLights": -2,
            "ParametricHighlights": -6,
            "ParametricShadowSplit": 25,
            "ParametricMidtoneSplit": 50,
            "ParametricHighlightSplit": 75,
        }
    return {}


def color_grading_settings(scene: str, aesthetic: str) -> dict[str, int]:
    if aesthetic in {"sweet", "warm_soft", "commercial_clean"}:
        return {
            "SplitToningHighlightHue": 42,
            "SplitToningHighlightSaturation": 6,
            "SplitToningShadowHue": 220,
            "SplitToningShadowSaturation": 3,
            "SplitToningBalance": 15,
        }
    if aesthetic in {"master", "texture", "high_gray"}:
        return {
            "SplitToningHighlightHue": 45,
            "SplitToningHighlightSaturation": 3,
            "SplitToningShadowHue": 220,
            "SplitToningShadowSaturation": 7,
            "SplitToningBalance": -5,
        }
    if aesthetic == "film":
        return {
            "SplitToningHighlightHue": 48,
            "SplitToningHighlightSaturation": 7,
            "SplitToningShadowHue": 210,
            "SplitToningShadowSaturation": 7,
            "SplitToningBalance": 0,
        }
    if scene == "sunset":
        return {
            "SplitToningHighlightHue": 38,
            "SplitToningHighlightSaturation": 8,
            "SplitToningShadowHue": 245,
            "SplitToningShadowSaturation": 4,
            "SplitToningBalance": 20,
        }
    if scene == "night":
        return {
            "SplitToningHighlightHue": 45,
            "SplitToningHighlightSaturation": 4,
            "SplitToningShadowHue": 235,
            "SplitToningShadowSaturation": 8,
            "SplitToningBalance": -15,
        }
    return {}


def crop_lightroom_settings(suggestion: dict[str, Any]) -> dict[str, Any]:
    if not suggestion.get("enabled"):
        return {}
    crop = suggestion.get("crop") or {}
    required = {"left", "top", "right", "bottom"}
    if not required.issubset(crop):
        return {}
    left = _clamp(float(crop["left"]), 0.0, 0.95)
    top = _clamp(float(crop["top"]), 0.0, 0.95)
    right = _clamp(float(crop["right"]), 0.05, 1.0)
    bottom = _clamp(float(crop["bottom"]), 0.05, 1.0)
    if right <= left or bottom <= top:
        return {}
    return {
        "CropLeft": round(left, 4),
        "CropTop": round(top, 4),
        "CropRight": round(right, 4),
        "CropBottom": round(bottom, 4),
        "CropAngle": 0,
    }


def mask_execution_plan(scene: str, aesthetic: str, metrics: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    dark_ratio = float(metrics.get("dark_ratio", 0))
    bright_ratio = float(metrics.get("bright_ratio", 0))

    if scene in {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}:
        notes.append("人脸/主体蒙版：建议在外部 TIFF 精修阶段执行人脸提亮、皮肤纹理控制。")
        if dark_ratio > 0.25:
            notes.append("背景蒙版：建议压暗背景并保持主体亮度。")
    if scene in {"landscape", "blue_sky", "sunset"} and bright_ratio > 0.18:
        notes.append("天空蒙版：建议单独压高光、加去朦胧。")
    if scene in {"grass_tree", "forest"}:
        notes.append("绿色区域蒙版：建议局部降低绿色饱和度并提升层次。")
    return notes


def _add(settings: dict[str, int], kind: str, color: str, value: int) -> None:
    key = f"{kind}Adjustment{color}"
    settings[key] = settings.get(key, 0) + value


def _clamp_settings(settings: dict[str, int], low: int, high: int) -> dict[str, int]:
    return {key: int(_clamp(value, low, high)) for key, value in settings.items() if value != 0}


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
