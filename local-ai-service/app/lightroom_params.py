from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Mapping


PARAM_RANGES: dict[str, tuple[float, float]] = {
    "exposure": (-0.8, 0.8),
    "contrast": (-25, 30),
    "highlights": (-80, 20),
    "shadows": (-30, 60),
    "whites": (-30, 35),
    "blacks": (-35, 25),
    "temperature": (-900, 900),
    "tint": (-25, 25),
    "texture": (-30, 20),
    "clarity": (-25, 25),
    "dehaze": (-15, 20),
    "vibrance": (-15, 40),
    "saturation": (-20, 20),
    "sharpening": (0, 80),
    "noise_reduction": (0, 55),
}

DELTA_RANGES: dict[str, tuple[float, float]] = {
    "exposure": (-0.15, 0.15),
    "contrast": (-8, 8),
    "highlights": (-12, 12),
    "shadows": (-12, 12),
    "whites": (-8, 8),
    "blacks": (-8, 8),
    "temperature": (-250, 250),
    "tint": (-6, 6),
    "texture": (-8, 8),
    "clarity": (-8, 8),
    "dehaze": (-5, 5),
    "vibrance": (-6, 6),
    "saturation": (-5, 5),
    "sharpening": (-8, 8),
    "noise_reduction": (-8, 8),
}

DEFAULT_PARAMS: dict[str, float] = {
    "exposure": 0,
    "contrast": 0,
    "highlights": 0,
    "shadows": 0,
    "whites": 0,
    "blacks": 0,
    "temperature": 0,
    "tint": 0,
    "texture": 0,
    "clarity": 0,
    "dehaze": 0,
    "vibrance": 0,
    "saturation": 0,
    "sharpening": 30,
    "noise_reduction": 12,
}

STYLE_BASES: dict[str, dict[str, float]] = {
    "natural_portrait": {
        "contrast": 6,
        "highlights": -18,
        "shadows": 16,
        "whites": 4,
        "blacks": -5,
        "texture": -6,
        "clarity": -3,
        "vibrance": 8,
        "saturation": -2,
        "sharpening": 32,
        "noise_reduction": 16,
    },
    "wedding_clean": {
        "contrast": 4,
        "highlights": -28,
        "shadows": 20,
        "whites": 8,
        "blacks": -4,
        "temperature": 80,
        "texture": -10,
        "clarity": -5,
        "vibrance": 7,
        "saturation": -3,
        "sharpening": 28,
        "noise_reduction": 20,
    },
    "kids_soft": {
        "contrast": 2,
        "highlights": -22,
        "shadows": 18,
        "whites": 5,
        "blacks": -2,
        "temperature": 120,
        "texture": -12,
        "clarity": -7,
        "vibrance": 10,
        "saturation": -2,
        "sharpening": 25,
        "noise_reduction": 22,
    },
    "indoor_portrait": {
        "contrast": 8,
        "highlights": -24,
        "shadows": 24,
        "whites": 3,
        "blacks": -7,
        "temperature": -80,
        "texture": -8,
        "clarity": -4,
        "vibrance": 9,
        "saturation": -2,
        "sharpening": 30,
        "noise_reduction": 24,
    },
    "outdoor_backlight": {
        "contrast": 10,
        "highlights": -42,
        "shadows": 34,
        "whites": 6,
        "blacks": -8,
        "temperature": 40,
        "texture": -5,
        "clarity": -2,
        "dehaze": 2,
        "vibrance": 12,
        "saturation": -1,
        "sharpening": 34,
        "noise_reduction": 16,
    },
}

SCENE_BASES: dict[str, dict[str, float]] = {
    "auto": {},
    "portrait": STYLE_BASES["natural_portrait"],
    "wedding": STYLE_BASES["wedding_clean"],
    "children": STYLE_BASES["kids_soft"],
    "indoor_portrait": STYLE_BASES["indoor_portrait"],
    "outdoor_backlight": STYLE_BASES["outdoor_backlight"],
    "landscape": {
        "contrast": 14,
        "highlights": -28,
        "shadows": 18,
        "whites": 8,
        "blacks": -12,
        "texture": 12,
        "clarity": 10,
        "dehaze": 8,
        "vibrance": 18,
        "saturation": 2,
        "sharpening": 48,
        "noise_reduction": 12,
    },
    "flower": {
        "contrast": 8,
        "highlights": -20,
        "shadows": 10,
        "whites": 4,
        "blacks": -6,
        "texture": 6,
        "clarity": 3,
        "vibrance": 18,
        "saturation": 4,
        "sharpening": 42,
        "noise_reduction": 10,
    },
    "grass_tree": {
        "contrast": 10,
        "highlights": -24,
        "shadows": 22,
        "whites": 3,
        "blacks": -9,
        "texture": 10,
        "clarity": 8,
        "dehaze": 4,
        "vibrance": 10,
        "saturation": -3,
        "sharpening": 46,
        "noise_reduction": 12,
    },
    "forest": {
        "contrast": 12,
        "highlights": -30,
        "shadows": 32,
        "whites": 2,
        "blacks": -10,
        "texture": 12,
        "clarity": 8,
        "dehaze": 6,
        "vibrance": 8,
        "saturation": -4,
        "sharpening": 46,
        "noise_reduction": 16,
    },
    "architecture": {
        "contrast": 12,
        "highlights": -22,
        "shadows": 16,
        "whites": 7,
        "blacks": -10,
        "texture": 10,
        "clarity": 12,
        "dehaze": 4,
        "vibrance": 6,
        "saturation": -2,
        "sharpening": 50,
        "noise_reduction": 10,
    },
    "sunset": {
        "contrast": 10,
        "highlights": -38,
        "shadows": 16,
        "whites": 4,
        "blacks": -8,
        "temperature": 160,
        "texture": 4,
        "clarity": 6,
        "dehaze": 8,
        "vibrance": 20,
        "saturation": 4,
        "sharpening": 40,
        "noise_reduction": 14,
    },
    "blue_sky": {
        "contrast": 8,
        "highlights": -26,
        "shadows": 10,
        "whites": 8,
        "blacks": -6,
        "temperature": -80,
        "texture": 4,
        "clarity": 5,
        "dehaze": 6,
        "vibrance": 14,
        "saturation": 0,
        "sharpening": 40,
        "noise_reduction": 10,
    },
    "night": {
        "exposure": 0.08,
        "contrast": 8,
        "highlights": -45,
        "shadows": 28,
        "whites": -4,
        "blacks": -8,
        "temperature": -80,
        "clarity": 6,
        "dehaze": 5,
        "vibrance": 8,
        "saturation": -2,
        "sharpening": 35,
        "noise_reduction": 36,
    },
    "food": {
        "exposure": 0.08,
        "contrast": 8,
        "highlights": -18,
        "shadows": 12,
        "whites": 4,
        "blacks": -5,
        "temperature": 120,
        "texture": 5,
        "clarity": 3,
        "vibrance": 14,
        "saturation": 2,
        "sharpening": 42,
        "noise_reduction": 12,
    },
    "still_life": {
        "contrast": 10,
        "highlights": -20,
        "shadows": 14,
        "whites": 4,
        "blacks": -8,
        "texture": 8,
        "clarity": 6,
        "vibrance": 8,
        "saturation": -1,
        "sharpening": 44,
        "noise_reduction": 12,
    },
}

AESTHETIC_BASES: dict[str, dict[str, float]] = {
    "auto": {},
    "natural": {},
    "sweet": {
        "exposure": 0.12,
        "contrast": -4,
        "highlights": -8,
        "shadows": 10,
        "temperature": 80,
        "texture": -8,
        "clarity": -7,
        "vibrance": 8,
        "saturation": -1,
        "noise_reduction": 8,
    },
    "texture": {
        "contrast": 10,
        "highlights": -8,
        "shadows": -4,
        "blacks": -8,
        "texture": 14,
        "clarity": 12,
        "dehaze": 4,
        "vibrance": 2,
        "saturation": -4,
        "sharpening": 14,
    },
    "master": {
        "contrast": 8,
        "highlights": -18,
        "shadows": 6,
        "whites": 0,
        "blacks": -10,
        "temperature": -40,
        "texture": 4,
        "clarity": 6,
        "vibrance": -2,
        "saturation": -6,
        "sharpening": 8,
    },
    "japanese_clear": {
        "exposure": 0.18,
        "contrast": -6,
        "highlights": -18,
        "shadows": 18,
        "whites": 8,
        "blacks": 4,
        "temperature": -60,
        "texture": -6,
        "clarity": -6,
        "vibrance": 6,
        "saturation": -4,
    },
    "film": {
        "contrast": 6,
        "highlights": -16,
        "shadows": 8,
        "whites": -2,
        "blacks": 5,
        "temperature": 90,
        "texture": 4,
        "clarity": 2,
        "vibrance": 2,
        "saturation": -5,
        "sharpening": -4,
    },
    "commercial_clean": {
        "exposure": 0.08,
        "contrast": 4,
        "highlights": -26,
        "shadows": 16,
        "whites": 8,
        "blacks": -4,
        "texture": -4,
        "clarity": -2,
        "vibrance": 6,
        "saturation": -2,
        "sharpening": 4,
        "noise_reduction": 6,
    },
    "documentary": {
        "contrast": 4,
        "highlights": -10,
        "shadows": 6,
        "whites": 0,
        "blacks": -4,
        "texture": 2,
        "clarity": 2,
        "vibrance": 0,
        "saturation": -2,
    },
    "warm_soft": {
        "exposure": 0.1,
        "contrast": -4,
        "highlights": -12,
        "shadows": 12,
        "temperature": 180,
        "texture": -8,
        "clarity": -8,
        "vibrance": 6,
        "saturation": -2,
    },
    "cool_transparent": {
        "exposure": 0.12,
        "contrast": 2,
        "highlights": -18,
        "shadows": 14,
        "whites": 8,
        "blacks": -2,
        "temperature": -180,
        "clarity": 2,
        "dehaze": 2,
        "vibrance": 8,
        "saturation": -1,
    },
    "high_gray": {
        "contrast": -2,
        "highlights": -16,
        "shadows": 10,
        "whites": -3,
        "blacks": 6,
        "temperature": -40,
        "texture": 2,
        "clarity": 4,
        "vibrance": -8,
        "saturation": -10,
    },
}

LEGACY_STYLE_TO_SCENE_AESTHETIC: dict[str, tuple[str, str]] = {
    "natural_portrait": ("portrait", "natural"),
    "wedding_clean": ("wedding", "commercial_clean"),
    "kids_soft": ("children", "warm_soft"),
    "indoor_portrait": ("indoor_portrait", "natural"),
    "outdoor_backlight": ("outdoor_backlight", "cool_transparent"),
}

LIGHTROOM_SETTING_MAP: dict[str, str] = {
    "exposure": "Exposure2012",
    "contrast": "Contrast2012",
    "highlights": "Highlights2012",
    "shadows": "Shadows2012",
    "whites": "Whites2012",
    "blacks": "Blacks2012",
    "temperature": "TemperatureDelta",
    "tint": "Tint",
    "texture": "Texture",
    "clarity": "Clarity2012",
    "dehaze": "Dehaze",
    "vibrance": "Vibrance",
    "saturation": "Saturation",
    "sharpening": "Sharpness",
    "noise_reduction": "LuminanceSmoothing",
}


@dataclass(frozen=True)
class ParameterPlan:
    params: dict[str, float]
    lightroom_settings: dict[str, float]


def supported_styles() -> list[str]:
    return sorted(STYLE_BASES)


def supported_scenes() -> list[str]:
    return sorted(SCENE_BASES)


def supported_aesthetics() -> list[str]:
    return sorted(AESTHETIC_BASES)


def supported_edit_levels() -> list[str]:
    return ["basic", "basic_plus_advanced_suggestions", "basic_plus_advanced_execute"]


def clamp_value(name: str, value: float, ranges: Mapping[str, tuple[float, float]] = PARAM_RANGES) -> float:
    if name not in ranges:
        return value
    low, high = ranges[name]
    return min(max(value, low), high)


def clamp_params(
    params: Mapping[str, float],
    ranges: Mapping[str, tuple[float, float]] = PARAM_RANGES,
) -> dict[str, float]:
    clean = dict(DEFAULT_PARAMS)
    for key, value in params.items():
        if key in DEFAULT_PARAMS:
            clean[key] = clamp_value(key, float(value), ranges)
    return round_params(clean)


def clamp_partial_params(
    params: Mapping[str, float],
    ranges: Mapping[str, tuple[float, float]] = PARAM_RANGES,
) -> dict[str, float]:
    return {
        key: round_params({key: clamp_value(key, float(value), ranges)})[key]
        for key, value in params.items()
        if key in DEFAULT_PARAMS
    }


def round_params(params: Mapping[str, float]) -> dict[str, float]:
    rounded: dict[str, float] = {}
    for key, value in params.items():
        if key == "exposure":
            rounded[key] = round(float(value), 2)
        elif key in {"temperature", "tint"}:
            rounded[key] = int(round(float(value)))
        else:
            rounded[key] = int(round(float(value)))
    return rounded


def add_params(*parts: Mapping[str, float]) -> dict[str, float]:
    merged = clamp_params(parts[0] if parts else DEFAULT_PARAMS)
    for part in parts[1:]:
        for key, value in part.items():
            if key in merged:
                merged[key] = float(merged[key]) + float(value)
    return clamp_params(merged)


def clamp_deltas(deltas: Mapping[str, float]) -> dict[str, float]:
    return {
        key: round_params({key: clamp_value(key, float(value), DELTA_RANGES)})[key]
        for key, value in deltas.items()
        if key in DELTA_RANGES
    }


def style_base(style: str) -> dict[str, float]:
    return clamp_params(STYLE_BASES.get(style, STYLE_BASES["natural_portrait"]))


def resolve_scene_aesthetic(style: str | None, scene: str | None, aesthetic: str | None) -> tuple[str, str]:
    resolved_scene = scene or "auto"
    resolved_aesthetic = aesthetic or "natural"
    if resolved_scene == "auto" and style in LEGACY_STYLE_TO_SCENE_AESTHETIC:
        resolved_scene, legacy_aesthetic = LEGACY_STYLE_TO_SCENE_AESTHETIC[style]
        if resolved_aesthetic == "auto":
            resolved_aesthetic = legacy_aesthetic
    if resolved_scene not in SCENE_BASES:
        resolved_scene = "portrait"
    if resolved_aesthetic not in AESTHETIC_BASES:
        resolved_aesthetic = "natural"
    return resolved_scene, resolved_aesthetic


def scene_aesthetic_base(scene: str, aesthetic: str) -> dict[str, float]:
    return add_params(
        SCENE_BASES.get(scene, SCENE_BASES["portrait"]),
        AESTHETIC_BASES.get(aesthetic, AESTHETIC_BASES["natural"]),
    )


def metric_adjustments(metrics: Mapping[str, float], group: bool = False) -> dict[str, float]:
    avg_luma = float(metrics.get("avg_luma", 128))
    bright_ratio = float(metrics.get("bright_ratio", 0))
    dark_ratio = float(metrics.get("dark_ratio", 0))
    highlight_clip = float(metrics.get("highlight_clip", 0))
    shadow_clip = float(metrics.get("shadow_clip", 0))
    warmth = float(metrics.get("warmth", 0))
    saturation = float(metrics.get("avg_saturation", 45))
    sharpness = float(metrics.get("sharpness", 18))

    scale = 0.55 if group else 1.0
    exposure = ((128 - avg_luma) / 128) * 0.45 * scale

    adjustments: dict[str, float] = {
        "exposure": exposure,
        "highlights": -min(35, bright_ratio * 90 + highlight_clip * 350) * scale,
        "shadows": min(32, dark_ratio * 70 + shadow_clip * 180) * scale,
        "temperature": -warmth * 4.0 * scale,
    }

    if avg_luma < 95:
        adjustments["shadows"] = adjustments.get("shadows", 0) + 8 * scale
    if avg_luma > 170:
        adjustments["exposure"] = adjustments.get("exposure", 0) - 0.12 * scale
        adjustments["highlights"] = adjustments.get("highlights", 0) - 8 * scale
    if saturation > 75:
        adjustments["vibrance"] = -4 * scale
        adjustments["saturation"] = -3 * scale
    elif saturation < 30:
        adjustments["vibrance"] = 6 * scale
    if sharpness < 11:
        adjustments["sharpening"] = 6 * scale

    return clamp_partial_params(adjustments)


def make_group_base(style: str, sample_metrics: list[Mapping[str, float]], scene: str | None = None, aesthetic: str | None = None) -> dict[str, float]:
    resolved_scene, resolved_aesthetic = resolve_scene_aesthetic(style, scene, aesthetic)
    base = scene_aesthetic_base(resolved_scene, resolved_aesthetic)
    if not sample_metrics:
        return base

    aggregate: dict[str, float] = {}
    keys = set().union(*(m.keys() for m in sample_metrics))
    for key in keys:
        values = [float(m[key]) for m in sample_metrics if isinstance(m.get(key), Real)]
        if values:
            aggregate[key] = sum(values) / len(values)
    return add_params(base, metric_adjustments(aggregate, group=True))


def make_photo_params(group_base: Mapping[str, float], metrics: Mapping[str, float]) -> ParameterPlan:
    params = add_params(group_base, metric_adjustments(metrics, group=False))
    return ParameterPlan(params=params, lightroom_settings=to_lightroom_settings(params))


def to_lightroom_settings(params: Mapping[str, float]) -> dict[str, float]:
    clean = clamp_params(params)
    settings = {LIGHTROOM_SETTING_MAP[key]: value for key, value in clean.items() if key in LIGHTROOM_SETTING_MAP}
    if "noise_reduction" in clean:
        settings["ColorNoiseReduction"] = int(round(clean["noise_reduction"] * 0.6))
    settings["ProcessVersion"] = "15.4"
    return settings


def apply_deltas(params: Mapping[str, float], deltas: Mapping[str, float]) -> ParameterPlan:
    safe_deltas = clamp_deltas(deltas)
    merged = add_params(params, safe_deltas)
    return ParameterPlan(params=merged, lightroom_settings=to_lightroom_settings(merged))
