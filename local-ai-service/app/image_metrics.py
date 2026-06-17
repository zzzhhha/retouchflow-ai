from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any
import colorsys

from PIL import Image, ImageFilter, ImageStat


def _open_preview(path: str | Path) -> Image.Image:
    image_path = Path(path)
    if not image_path.exists():
        raise FileNotFoundError(f"Preview image not found: {image_path}")
    image = Image.open(image_path).convert("RGB")
    image.thumbnail((640, 640))
    return image


def _percentile(sorted_values: list[float], percent: float) -> float:
    if not sorted_values:
        return 0
    index = int(round((len(sorted_values) - 1) * percent))
    return sorted_values[index]


def image_metrics(path: str | Path) -> dict[str, float | int | str]:
    image = _open_preview(path)
    pixels = list(image.getdata())
    count = max(len(pixels), 1)

    lumas: list[float] = []
    saturations: list[float] = []
    warmth_values: list[float] = []
    tint_values: list[float] = []
    green_pixels = 0
    blue_pixels = 0
    skin_tone_pixels = 0
    warm_orange_pixels = 0
    dry_vegetation_pixels = 0

    for red, green, blue in pixels:
        luma = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        max_channel = max(red, green, blue)
        min_channel = min(red, green, blue)
        saturation = 0 if max_channel == 0 else (max_channel - min_channel) / max_channel * 100
        hue, hsv_saturation, value = colorsys.rgb_to_hsv(red / 255, green / 255, blue / 255)
        hue_degrees = hue * 360
        lumas.append(luma)
        saturations.append(saturation)
        warmth_values.append(red - blue)
        tint_values.append(green - ((red + blue) / 2))
        if value > 0.18 and hsv_saturation > 0.18 and 70 <= hue_degrees <= 170:
            green_pixels += 1
        if value > 0.25 and hsv_saturation > 0.16 and 185 <= hue_degrees <= 255:
            blue_pixels += 1
        if value > 0.22 and 8 <= hue_degrees <= 50 and 0.16 <= hsv_saturation <= 0.68 and red > blue:
            skin_tone_pixels += 1
        if value > 0.2 and hsv_saturation > 0.22 and 20 <= hue_degrees <= 65:
            warm_orange_pixels += 1
        if value > 0.16 and 20 <= hue_degrees <= 70 and 0.08 <= hsv_saturation <= 0.58 and red >= blue:
            dry_vegetation_pixels += 1

    lumas_sorted = sorted(lumas)
    edge_image = image.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_stat = ImageStat.Stat(edge_image)
    luma_stat = ImageStat.Stat(image.convert("L"))

    return {
        "path": str(path),
        "width": image.width,
        "height": image.height,
        "avg_luma": round(mean(lumas), 2),
        "p05_luma": round(_percentile(lumas_sorted, 0.05), 2),
        "p50_luma": round(_percentile(lumas_sorted, 0.50), 2),
        "p95_luma": round(_percentile(lumas_sorted, 0.95), 2),
        "highlight_clip": round(sum(1 for value in lumas if value >= 248) / count, 4),
        "shadow_clip": round(sum(1 for value in lumas if value <= 7) / count, 4),
        "bright_ratio": round(sum(1 for value in lumas if value >= 205) / count, 4),
        "dark_ratio": round(sum(1 for value in lumas if value <= 55) / count, 4),
        "avg_saturation": round(mean(saturations), 2),
        "green_ratio": round(green_pixels / count, 4),
        "blue_ratio": round(blue_pixels / count, 4),
        "skin_tone_ratio": round(skin_tone_pixels / count, 4),
        "warm_orange_ratio": round(warm_orange_pixels / count, 4),
        "dry_vegetation_ratio": round(dry_vegetation_pixels / count, 4),
        "warmth": round(mean(warmth_values), 2),
        "tint_bias": round(mean(tint_values), 2),
        "sharpness": round(edge_stat.mean[0], 2),
        "luma_stddev": round(luma_stat.stddev[0], 2),
    }


def compare_metrics(before_path: str | Path, after_path: str | Path) -> dict[str, Any]:
    before = image_metrics(before_path)
    after = image_metrics(after_path)
    return {
        "before": before,
        "after": after,
        "delta": {
            "avg_luma": round(float(after["avg_luma"]) - float(before["avg_luma"]), 2),
            "avg_saturation": round(float(after["avg_saturation"]) - float(before["avg_saturation"]), 2),
            "warmth": round(float(after["warmth"]) - float(before["warmth"]), 2),
            "highlight_clip": round(float(after["highlight_clip"]) - float(before["highlight_clip"]), 4),
            "shadow_clip": round(float(after["shadow_clip"]) - float(before["shadow_clip"]), 4),
        },
    }
