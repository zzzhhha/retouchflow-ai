from __future__ import annotations

import json
from typing import Any

from .advanced_edits import build_advanced_plan
from .ai_connection import call_ai_text
from .config import AIConfig, load_ai_config
from .external_ai import analyze_with_external_ai, external_ai_enabled
from .image_metrics import image_metrics
from .lightroom_params import apply_deltas, make_group_base, make_photo_params, resolve_scene_aesthetic, supported_scenes
from .local_regions import analyze_local_regions
from .schemas import AnalyzeRequest, AnalyzeResponse, GroupStyle, PhotoPlan
from .user_intent import (
    apply_crop_intent,
    clean_user_suggestion,
    parameter_deltas_from_user_suggestion,
    user_suggestion_for_photo,
    user_suggestion_notes,
)


SAFE_METRIC_KEYS = [
    "width",
    "height",
    "avg_luma",
    "p05_luma",
    "p50_luma",
    "p95_luma",
    "highlight_clip",
    "shadow_clip",
    "bright_ratio",
    "dark_ratio",
    "avg_saturation",
    "green_ratio",
    "blue_ratio",
    "skin_tone_ratio",
    "warm_orange_ratio",
    "dry_vegetation_ratio",
    "warmth",
    "tint_bias",
    "sharpness",
    "luma_stddev",
]

SCENE_ALIASES = {
    "人像": "portrait",
    "婚纱": "wedding",
    "儿童": "children",
    "室内写真": "indoor_portrait",
    "户外逆光": "outdoor_backlight",
    "风景": "landscape",
    "花草": "flower",
    "花": "flower",
    "草地树木": "grass_tree",
    "树林": "forest",
    "森林": "forest",
    "建筑": "architecture",
    "日落": "sunset",
    "晚霞": "sunset",
    "蓝天白云": "blue_sky",
    "夜景": "night",
    "美食": "food",
    "静物": "still_life",
}


class Planner:
    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        scene, aesthetic = resolve_scene_aesthetic(request.style, request.scene, request.aesthetic)
        edit_level = request.edit_level
        user_suggestion = clean_user_suggestion(request.user_suggestion)
        ai_config = load_ai_config()
        metrics_by_photo: list[tuple[Any, dict[str, Any]]] = []
        for photo in request.photos:
            metrics_by_photo.append((photo, image_metrics(photo.preview_path)))

        external_fallback_status: dict[str, Any] | None = None
        if external_ai_enabled(ai_config):
            external_response, external_fallback_status = analyze_with_external_ai(
                request,
                ai_config,
                metrics_by_photo,
                scene,
                aesthetic,
                edit_level,
            )
            if external_response is not None:
                return external_response

        sample = [metrics for _, metrics in metrics_by_photo[:10]]
        group_base = make_group_base(request.style, sample, scene=scene, aesthetic=aesthetic)
        base_by_scene: dict[str, dict[str, float | int]] = {scene: group_base}
        plans: list[PhotoPlan] = []

        photo_count = len(metrics_by_photo)
        for index, (photo, metrics) in enumerate(metrics_by_photo):
            photo_suggestion = user_suggestion_for_photo(user_suggestion, index, photo_count)
            photo_scene = infer_photo_scene(metrics, scene, request.scene)
            if photo_scene not in base_by_scene:
                base_by_scene[photo_scene] = make_group_base(request.style, sample, scene=photo_scene, aesthetic=aesthetic)
            plan = make_photo_params(base_by_scene[photo_scene], metrics)
            user_deltas = parameter_deltas_from_user_suggestion(photo_suggestion, photo_scene)
            if user_deltas:
                plan = apply_deltas(plan.params, user_deltas)
            crop = apply_crop_intent(crop_suggestion(metrics, photo_scene, aesthetic), photo_suggestion)
            local_analysis = analyze_local_regions(photo.preview_path, metrics, photo_scene, aesthetic, user_suggestion=photo_suggestion)
            advanced_plan = build_advanced_plan(metrics, photo_scene, aesthetic, edit_level, crop, local_analysis)
            lightroom_settings = dict(plan.lightroom_settings)
            lightroom_settings.update(advanced_plan.get("lightroom_settings", {}))
            plans.append(
                PhotoPlan(
                    photo_id=photo.photo_id,
                    file_name=photo.file_name,
                    detected_scene=photo_scene,
                    params=plan.params,
                    lightroom_settings=lightroom_settings,
                    metrics=metrics,
                    local_analysis=local_analysis,
                    crop_suggestion=crop,
                    advanced_plan=advanced_plan,
                    advanced_suggestions=advanced_suggestions(metrics, photo_scene, aesthetic, edit_level, photo_suggestion),
                )
            )

        ai_status = external_fallback_status or {
            "mode": "rules",
            "requested_external_ai": False,
            "used_external_ai": False,
            "source": "rules",
            "provider": ai_config.provider,
            "model": ai_config.model,
            "wire_api": ai_config.wire_api,
            "message": "外部 AI 未启用，使用本地规则生成修图方案。",
        }

        return AnalyzeResponse(
            batch_id=request.batch_id,
            style=request.style,
            scene=scene,
            aesthetic=aesthetic,
            edit_level=edit_level,
            user_suggestion=user_suggestion,
            ai_status=ai_status,
            group_style=GroupStyle(
                style=request.style,
                scene=scene,
                aesthetic=aesthetic,
                edit_level=edit_level,
                skin_tone_target=skin_target(scene, aesthetic),
                contrast_level=contrast_level(aesthetic),
                base_params=group_base,
            ),
            photos=plans,
        )


def apply_external_ai_if_enabled(
    request: AnalyzeRequest,
    config: AIConfig,
    plans: list[PhotoPlan],
    scene: str,
    aesthetic: str,
    edit_level: str,
) -> tuple[list[PhotoPlan], dict[str, Any]]:
    if not config.enabled or config.provider == "mock":
        return plans, {
            "mode": "rules",
            "requested_external_ai": False,
            "used_external_ai": False,
            "source": "rules",
            "provider": config.provider,
            "model": config.model,
            "wire_api": config.wire_api,
            "message": "外部 AI 未启用，使用本地规则生成修图参数。",
        }

    prompt = build_external_ai_prompt(request, plans, scene, aesthetic, edit_level)
    result = call_ai_text(config, prompt, max_tokens=2200, timeout=75)
    if not result.get("passed"):
        return plans, _external_ai_fallback_status(config, result, str(result.get("message") or "外部 AI 调用失败，已回退本地规则。"))

    try:
        ai_payload = parse_ai_json(str(result.get("text") or result.get("sample") or ""))
    except ValueError as exc:
        return plans, _external_ai_fallback_status(config, result, f"外部 AI 返回内容不是可解析的 JSON，已回退本地规则。{exc}")

    overrides = photo_overrides_by_id(ai_payload)
    updated_plans: list[PhotoPlan] = []
    applied_count = 0
    for plan in plans:
        override = overrides.get(plan.photo_id)
        if not override:
            updated_plans.append(plan)
            continue

        updated = apply_ai_override(plan, override, aesthetic, edit_level)
        if updated.ai_source == "external_ai":
            applied_count += 1
        updated_plans.append(updated)

    if applied_count == 0:
        return plans, _external_ai_fallback_status(config, result, "外部 AI 已返回内容，但没有匹配到任何照片修正，已回退本地规则。")

    batch_notes = str(ai_payload.get("batch_notes") or ai_payload.get("notes") or "外部 AI 已参与本批次参数决策。")
    return updated_plans, {
        "mode": "external_ai",
        "requested_external_ai": True,
        "used_external_ai": True,
        "source": provider_label(config),
        "provider": config.provider,
        "model": config.model,
        "wire_api": result.get("wire_api", config.wire_api),
        "endpoint": result.get("endpoint", ""),
        "latency_ms": result.get("latency_ms"),
        "applied_photo_count": applied_count,
        "photo_count": len(plans),
        "message": batch_notes[:240],
    }


def build_external_ai_prompt(
    request: AnalyzeRequest,
    plans: list[PhotoPlan],
    scene: str,
    aesthetic: str,
    edit_level: str,
) -> str:
    batch_suggestion = clean_user_suggestion(request.user_suggestion)
    photos = [
        {
            "photo_id": plan.photo_id,
            "file_name": plan.file_name,
            "detected_scene": plan.detected_scene,
            "photo_user_suggestion": user_suggestion_for_photo(batch_suggestion, index, len(plans)),
            "metrics": public_metrics(plan.metrics),
            "rule_params": plan.params,
            "crop_suggestion": plan.crop_suggestion,
        }
        for index, plan in enumerate(plans)
    ]
    payload = {
        "batch_id": request.batch_id,
        "style": request.style,
        "requested_scene": request.scene,
        "resolved_scene": scene,
        "aesthetic": aesthetic,
        "edit_level": edit_level,
        "user_suggestion": batch_suggestion,
        "supported_scenes": supported_scenes(),
        "allowed_delta_params": [
            "exposure",
            "contrast",
            "highlights",
            "shadows",
            "whites",
            "blacks",
            "temperature",
            "tint",
            "texture",
            "clarity",
            "dehaze",
            "vibrance",
            "saturation",
            "sharpening",
            "noise_reduction",
        ],
        "photos": photos,
    }
    return (
        "你是 Lightroom Classic 批量初修助手。请根据每张照片的低清预览指标和本地规则初稿，给出小幅、克制的参数修正。\n"
        "要求：\n"
        "1. 只返回 JSON，不要 Markdown，不要解释性正文。\n"
        "2. 每张照片通过 photo_id 匹配；可以修正 scene，但 scene 必须使用 supported_scenes 里的英文值。\n"
        "3. deltas 是相对 rule_params 的修正量，不是最终绝对值；每个值都要小幅调整。\n"
        "3.1 如果 user_suggestion 使用“第一张/第二张/图1/图2”描述不同要求，必须以每张 photos[].photo_user_suggestion 为准。\n"
        "4. 混合批次中不要把纯风景、花草、草地树木误判成人像。\n"
        "5. dry_vegetation_ratio 高时通常是芦苇、枯草、黄褐色草木；不要仅因 skin_tone_ratio 高就判成人像。\n"
        "6. 返回格式：{\"batch_notes\":\"...\",\"photos\":[{\"photo_id\":\"...\",\"scene\":\"landscape\",\"deltas\":{\"exposure\":0.05,\"highlights\":-4},\"notes\":\"...\"}]}。\n"
        "待分析数据：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def public_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: metrics[key] for key in SAFE_METRIC_KEYS if key in metrics}


def parse_ai_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        clean = "\n".join(lines).strip()

    candidates = [clean]
    first = clean.find("{")
    last = clean.rfind("}")
    if first >= 0 and last > first:
        candidates.append(clean[first : last + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("未找到 JSON 对象。")


def photo_overrides_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    photos = payload.get("photos")
    if not isinstance(photos, list):
        photos = payload.get("photo_overrides")
    if not isinstance(photos, list):
        return {}

    overrides: dict[str, dict[str, Any]] = {}
    for item in photos:
        if not isinstance(item, dict):
            continue
        photo_id = str(item.get("photo_id") or "").strip()
        if photo_id:
            overrides[photo_id] = item
    return overrides


def apply_ai_override(plan: PhotoPlan, override: dict[str, Any], aesthetic: str, edit_level: str) -> PhotoPlan:
    scene = normalize_scene(str(override.get("scene") or override.get("detected_scene") or plan.detected_scene), plan.detected_scene)
    scene = guarded_scene_override(plan.metrics, scene, plan.detected_scene)
    deltas = override_deltas(plan.params, override)
    has_scene_change = scene != plan.detected_scene
    has_notes = bool(override_notes(override))
    if not deltas and not has_scene_change and not has_notes:
        return plan

    updated = apply_deltas(plan.params, deltas) if deltas else apply_deltas(plan.params, {})
    crop = crop_suggestion(plan.metrics, scene, aesthetic)
    advanced_plan = build_advanced_plan(plan.metrics, scene, aesthetic, edit_level, crop, plan.local_analysis)
    lightroom_settings = dict(updated.lightroom_settings)
    lightroom_settings.update(advanced_plan.get("lightroom_settings", {}))
    return plan.model_copy(
        update={
            "detected_scene": scene,
            "ai_source": "external_ai",
            "ai_notes": override_notes(override),
            "params": updated.params,
            "lightroom_settings": lightroom_settings,
            "crop_suggestion": crop,
            "advanced_plan": advanced_plan,
            "advanced_suggestions": advanced_suggestions(plan.metrics, scene, aesthetic, edit_level),
        }
    )


def normalize_scene(value: str, fallback: str = "auto") -> str:
    clean = value.strip()
    if clean in SCENE_ALIASES:
        clean = SCENE_ALIASES[clean]
    return clean if clean in set(supported_scenes()) else fallback


def guarded_scene_override(metrics: dict[str, Any], proposed_scene: str, current_scene: str) -> str:
    if proposed_scene in {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}:
        if looks_like_dry_vegetation(metrics):
            return "grass_tree"
        if looks_like_nature_scene(metrics) and not has_strong_portrait_signal(metrics):
            return current_scene if current_scene != "auto" else "landscape"
    return proposed_scene


def override_deltas(current_params: dict[str, float | int], override: dict[str, Any]) -> dict[str, float]:
    raw = override.get("deltas")
    if isinstance(raw, dict):
        return numeric_params(raw)

    target = override.get("params")
    if not isinstance(target, dict):
        target = override.get("lightroom_params")
    if not isinstance(target, dict):
        return {}

    deltas: dict[str, float] = {}
    for key, value in numeric_params(target).items():
        if key in current_params:
            deltas[key] = float(value) - float(current_params[key])
    return deltas


def numeric_params(values: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in values.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def override_notes(override: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    for key in ["notes", "reason", "comment"]:
        value = override.get(key)
        if isinstance(value, str) and value.strip():
            notes.append(value.strip()[:180])
    raw_notes = override.get("notes")
    if isinstance(raw_notes, list):
        for item in raw_notes:
            if isinstance(item, str) and item.strip():
                notes.append(item.strip()[:180])
    return notes[:4]


def _external_ai_fallback_status(config: AIConfig, result: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "mode": "rules_fallback",
        "requested_external_ai": True,
        "used_external_ai": False,
        "source": "rules",
        "external_source": provider_label(config),
        "provider": config.provider,
        "model": config.model,
        "wire_api": result.get("wire_api", config.wire_api),
        "endpoint": result.get("endpoint", ""),
        "latency_ms": result.get("latency_ms"),
        "message": message[:300],
    }


def provider_label(config: AIConfig) -> str:
    if config.provider == "openai_relay":
        return "中转站 API"
    if config.provider == "openai_compatible":
        return "OpenAI 兼容接口"
    if config.provider == "custom":
        return "自定义接口"
    return "规则模式"


def skin_target(scene: str, aesthetic: str) -> str:
    if scene in {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}:
        if aesthetic in {"sweet", "warm_soft", "commercial_clean"}:
            return "warm_clean"
        if aesthetic in {"texture", "master", "high_gray"}:
            return "neutral_texture"
        return "warm_neutral"
    return "not_primary"


def contrast_level(aesthetic: str) -> str:
    if aesthetic in {"sweet", "japanese_clear", "warm_soft", "high_gray"}:
        return "soft"
    if aesthetic in {"texture", "master", "landscape"}:
        return "strong"
    return "natural"


def looks_like_dry_vegetation(metrics: dict[str, Any]) -> bool:
    skin_ratio = float(metrics.get("skin_tone_ratio", 0))
    warm_orange_ratio = float(metrics.get("warm_orange_ratio", 0))
    dry_ratio = float(metrics.get("dry_vegetation_ratio", warm_orange_ratio))
    green_ratio = float(metrics.get("green_ratio", 0))
    blue_ratio = float(metrics.get("blue_ratio", 0))
    saturation = float(metrics.get("avg_saturation", 45))
    sharpness = float(metrics.get("sharpness", 0))
    luma_stddev = float(metrics.get("luma_stddev", 0))

    return (
        dry_ratio > 0.28
        and skin_ratio > 0.16
        and warm_orange_ratio > 0.18
        and saturation < 38
        and sharpness > 14
        and luma_stddev > 34
        and green_ratio + blue_ratio < 0.16
    )


def looks_like_nature_scene(metrics: dict[str, Any]) -> bool:
    green_ratio = float(metrics.get("green_ratio", 0))
    blue_ratio = float(metrics.get("blue_ratio", 0))
    warm_orange_ratio = float(metrics.get("warm_orange_ratio", 0))
    dry_ratio = float(metrics.get("dry_vegetation_ratio", 0))
    saturation = float(metrics.get("avg_saturation", 45))
    sharpness = float(metrics.get("sharpness", 0))
    return green_ratio > 0.12 or blue_ratio > 0.14 or dry_ratio > 0.22 or (warm_orange_ratio > 0.2 and saturation < 42 and sharpness > 12)


def has_strong_portrait_signal(metrics: dict[str, Any]) -> bool:
    skin_ratio = float(metrics.get("skin_tone_ratio", 0))
    warm_orange_ratio = float(metrics.get("warm_orange_ratio", 0))
    dry_ratio = float(metrics.get("dry_vegetation_ratio", 0))
    saturation = float(metrics.get("avg_saturation", 45))
    sharpness = float(metrics.get("sharpness", 0))
    luma_stddev = float(metrics.get("luma_stddev", 0))
    if looks_like_dry_vegetation(metrics):
        return False
    if dry_ratio > 0.28 and warm_orange_ratio > 0.18 and sharpness > 14 and saturation < 38:
        return False
    return skin_ratio >= 0.08 and not (skin_ratio > 0.35 and luma_stddev > 42 and sharpness > 16)


def infer_photo_scene(metrics: dict[str, Any], group_scene: str, requested_scene: str | None = None) -> str:
    width = float(metrics.get("width", 0) or 0)
    height = float(metrics.get("height", 0) or 0)
    aspect = width / height if height > 0 else 1.0
    green_ratio = float(metrics.get("green_ratio", 0))
    blue_ratio = float(metrics.get("blue_ratio", 0))
    skin_ratio = float(metrics.get("skin_tone_ratio", 0))
    warm_orange_ratio = float(metrics.get("warm_orange_ratio", 0))
    saturation = float(metrics.get("avg_saturation", 45))
    avg_luma = float(metrics.get("avg_luma", 128))
    dark_ratio = float(metrics.get("dark_ratio", 0))
    bright_ratio = float(metrics.get("bright_ratio", 0))

    if looks_like_dry_vegetation(metrics):
        return "grass_tree"
    if dark_ratio > 0.42 and avg_luma < 95:
        return "night"
    if green_ratio > 0.28 and skin_ratio < 0.08:
        return "forest" if dark_ratio > 0.24 else "grass_tree"
    if blue_ratio > 0.24 and bright_ratio > 0.12 and skin_ratio < 0.08:
        return "blue_sky"
    if warm_orange_ratio > 0.22 and saturation > 38 and skin_ratio < 0.08:
        return "sunset"
    if aspect > 1.25 and skin_ratio < 0.075 and (green_ratio + blue_ratio > 0.18 or saturation > 34):
        return "landscape"

    if group_scene == "auto":
        if has_strong_portrait_signal(metrics):
            return "portrait"
        if green_ratio > 0.16:
            return "grass_tree"
        if blue_ratio > 0.16:
            return "blue_sky"
        return "landscape" if aspect > 1.25 else "still_life"

    if group_scene in {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}:
        if looks_like_nature_scene(metrics) and not has_strong_portrait_signal(metrics):
            return "grass_tree" if looks_like_dry_vegetation(metrics) or green_ratio > blue_ratio else "landscape"
        if skin_ratio < 0.045 and aspect > 1.2 and (green_ratio + blue_ratio > 0.14 or saturation > 32):
            return "landscape"
        return group_scene

    return group_scene


def advanced_suggestions(metrics: dict[str, Any], scene: str, aesthetic: str, edit_level: str, user_suggestion: str = "") -> list[str]:
    if edit_level == "basic":
        return user_suggestion_notes(user_suggestion)

    suggestions: list[str] = user_suggestion_notes(user_suggestion)
    bright_ratio = float(metrics.get("bright_ratio", 0))
    dark_ratio = float(metrics.get("dark_ratio", 0))
    highlight_clip = float(metrics.get("highlight_clip", 0))
    saturation = float(metrics.get("avg_saturation", 45))
    sharpness = float(metrics.get("sharpness", 18))

    if scene in {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}:
        suggestions.append("建议检测人脸区域：必要时对人脸轻微提亮，并控制皮肤纹理。")
        if dark_ratio > 0.25:
            suggestions.append("建议检测主体与背景：主体提亮，背景保持或轻微压暗。")
    if scene in {"landscape", "blue_sky", "sunset"}:
        suggestions.append("建议检测天空区域：单独控制高光与去朦胧，避免天空过曝。")
    if scene in {"grass_tree", "forest"}:
        suggestions.append("建议使用混色器降低绿色饱和度，并微调绿色色相，避免绿得发荧光。")
    if scene == "flower":
        suggestions.append("建议检测花朵主体：提升主体细节，背景适度柔化。")
    if scene == "night":
        suggestions.append("建议分区降噪：暗部加强降噪，高光灯牌单独压低。")

    if highlight_clip > 0.03 or bright_ratio > 0.28:
        suggestions.append("建议建立高光蒙版，单独压低过亮区域。")
    if saturation > 70:
        suggestions.append("建议进入混色器，降低过饱和颜色的饱和度。")
    if sharpness < 10:
        suggestions.append("建议只对主体或纹理区域锐化，避免全图噪点变明显。")
    if aesthetic in {"master", "high_gray", "film"}:
        suggestions.append("建议增加曲线或色彩分级控制，让暗部和中间调更有层次。")

    return suggestions


def crop_suggestion(metrics: dict[str, Any], scene: str, aesthetic: str) -> dict[str, Any]:
    width = float(metrics.get("width", 0) or 0)
    height = float(metrics.get("height", 0) or 0)
    if width <= 0 or height <= 0:
        return {"enabled": False, "mode": "analysis", "aspect_ratio": "原比例", "crop": _full_crop(), "reason": "缺少尺寸信息，暂不建议裁剪。"}

    aspect = width / height
    skin_ratio = float(metrics.get("skin_tone_ratio", 0))
    green_ratio = float(metrics.get("green_ratio", 0))
    blue_ratio = float(metrics.get("blue_ratio", 0))
    dark_ratio = float(metrics.get("dark_ratio", 0))
    bright_ratio = float(metrics.get("bright_ratio", 0))

    if scene in {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}:
        if skin_ratio < 0.035 and aspect > 1.15:
            return {
                "enabled": False,
                "mode": "analysis",
                "aspect_ratio": "原比例",
                "crop": _full_crop(),
                "reason": "画面没有明显人物肤色区域，避免按人像 4:5 强行裁切。",
            }
        target = "4:5" if aspect > 0.95 else "原比例"
        crop = _center_crop_to_aspect(aspect, 0.8) if target == "4:5" else _full_crop()
        vertical_note = "上方保留更多环境" if bright_ratio > 0.18 else "保留人物头顶和下方空间"
        return {
            "enabled": target != "原比例",
            "mode": "suggestion",
            "aspect_ratio": target,
            "crop": crop,
            "reason": f"检测为人像，当前宽高比 {aspect:.2f}，可尝试 4:5 收紧左右边缘；{vertical_note}。"
            if target != "原比例"
            else f"检测为人像，当前宽高比 {aspect:.2f} 已较适合人物展示，暂不建议裁剪。",
        }

    if scene in {"landscape", "blue_sky", "sunset", "forest", "grass_tree"}:
        target = "16:9" if 1.0 < aspect < 1.62 else "原比例"
        crop = _center_crop_to_aspect(aspect, 16 / 9) if target == "16:9" else _full_crop()
        if scene in {"grass_tree", "forest"} and dark_ratio > 0.22:
            reason = f"检测为草木/森林，当前宽高比 {aspect:.2f}，建议轻裁上下杂乱暗部，突出层次。"
        elif scene == "blue_sky" and blue_ratio > 0.22:
            reason = f"检测到较多天空区域，当前宽高比 {aspect:.2f}，可裁掉部分空白天空或地面，保留横向开阔感。"
        else:
            reason = f"检测为风景，当前宽高比 {aspect:.2f}，可尝试 16:9 强化横向空间和画面层次。"
        return {
            "enabled": target != "原比例",
            "mode": "suggestion",
            "aspect_ratio": target,
            "crop": crop,
            "reason": reason
            if target != "原比例"
            else f"检测为风景/自然场景，当前宽高比 {aspect:.2f} 已较适合保留环境，暂不建议裁剪。",
        }

    if scene in {"flower", "food", "still_life"}:
        target = "1:1" if aesthetic in {"sweet", "commercial_clean", "japanese_clear"} else "4:5"
        target_aspect = 1.0 if target == "1:1" else 0.8
        return {
            "enabled": True,
            "mode": "suggestion",
            "aspect_ratio": target,
            "crop": _center_crop_to_aspect(aspect, target_aspect, min_margin=0.04),
            "reason": f"检测为主体类照片，当前宽高比 {aspect:.2f}，建议收紧边缘减少杂物，让主体更明确。",
        }

    return {
        "enabled": False,
        "mode": "suggestion",
        "aspect_ratio": "原比例",
        "crop": _full_crop(),
        "reason": "当前场景暂不建议自动裁剪。",
    }


def _full_crop() -> dict[str, float]:
    return {"left": 0, "top": 0, "right": 1, "bottom": 1}


def _center_crop_to_aspect(current_aspect: float, target_aspect: float, min_margin: float = 0.0) -> dict[str, float]:
    if current_aspect <= 0 or target_aspect <= 0:
        return _full_crop()
    if current_aspect > target_aspect:
        keep_width = max(0.1, min(1.0, target_aspect / current_aspect))
        margin = max((1 - keep_width) / 2, min_margin)
        return {"left": round(margin, 4), "top": 0, "right": round(1 - margin, 4), "bottom": 1}
    keep_height = max(0.1, min(1.0, current_aspect / target_aspect))
    margin = max((1 - keep_height) / 2, min_margin)
    return {"left": 0, "top": round(margin, 4), "right": 1, "bottom": round(1 - margin, 4)}
