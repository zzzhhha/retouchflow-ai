from __future__ import annotations

import base64
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from .advanced_edits import crop_lightroom_settings, vignette_lightroom_settings
from .ai_connection import call_ai_text
from .config import AIConfig
from .image_metrics import compare_metrics
from .lightroom_params import DEFAULT_PARAMS, apply_deltas, clamp_deltas, clamp_params, supported_scenes, to_lightroom_settings
from .local_regions import analyze_local_regions
from .schemas import AnalyzeRequest, AnalyzeResponse, GroupStyle, PhotoPlan, ReviewRequest, ReviewResponse, ReviewResult
from .user_intent import (
    apply_crop_intent,
    clean_user_suggestion,
    parameter_deltas_from_user_suggestion,
    parse_user_intent,
    user_suggestion_for_photo,
    user_suggestion_notes,
)


PARAM_KEYS = list(DEFAULT_PARAMS.keys())
SUPPORTED_SCENE_SET = set(supported_scenes())
SCENE_NAMES = {
    "auto": "自动识别",
    "portrait": "人像",
    "wedding": "婚纱",
    "children": "儿童",
    "indoor_portrait": "室内写真",
    "outdoor_backlight": "户外逆光",
    "landscape": "风景",
    "flower": "花卉",
    "grass_tree": "草地树木",
    "forest": "森林",
    "architecture": "城市建筑",
    "sunset": "日落晚霞",
    "blue_sky": "蓝天白云",
    "night": "夜景",
    "food": "美食",
    "still_life": "静物",
}
PORTRAIT_SCENES = {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}
NATURE_SCENES = {"landscape", "flower", "grass_tree", "forest", "sunset", "blue_sky", "night"}
ISSUE_ALIASES = {
    "too_dark": "too_dark",
    "too_bright": "too_bright",
    "highlights_clipped": "highlights_clipped",
    "shadows_blocked": "shadows_blocked",
    "over_saturated": "over_saturated",
    "too_warm": "too_warm",
    "too_cool": "too_cool",
}


def external_ai_enabled(config: AIConfig) -> bool:
    return config.enabled and config.provider != "mock" and bool(config.api_key) and bool(config.model)


def analyze_with_external_ai(
    request: AnalyzeRequest,
    config: AIConfig,
    metrics_by_photo: list[tuple[Any, dict[str, Any]]],
    resolved_scene: str,
    aesthetic: str,
    edit_level: str,
) -> tuple[AnalyzeResponse | None, dict[str, Any]]:
    user_suggestion = clean_user_suggestion(request.user_suggestion)
    prompt = _analysis_prompt(request, metrics_by_photo, resolved_scene, aesthetic, edit_level)
    image_urls = [_image_data_url(photo.preview_path) for photo, _ in metrics_by_photo]
    image_urls = [url for url in image_urls if url]
    result, used_images = _call_ai_with_image_fallback(config, prompt, image_urls, max_tokens=3600, timeout=90)
    if not result.get("passed"):
        return None, _fallback_status(config, result, str(result.get("message") or "外部 AI 分析调用失败。"))

    try:
        payload = _parse_json_object(str(result.get("text") or result.get("sample") or ""))
        plans = _plans_from_ai_payload(payload, metrics_by_photo, aesthetic, edit_level, user_suggestion)
    except ValueError as exc:
        return None, _fallback_status(config, result, f"外部 AI 分析结果不是有效 JSON：{exc}")

    if len(plans) != len(metrics_by_photo):
        return None, _fallback_status(config, result, "外部 AI 没有为每张照片返回完整修图方案。")

    group_scene = _group_scene(payload, plans, resolved_scene)
    base_params = _average_params([plan.params for plan in plans])
    raw_message = str(payload.get("batch_notes") or payload.get("notes") or "")
    ai_status = {
        "mode": "external_ai_vision" if used_images else "external_ai_text",
        "requested_external_ai": True,
        "used_external_ai": True,
        "source": _provider_label(config),
        "provider": config.provider,
        "model": config.model,
        "wire_api": result.get("wire_api", config.wire_api),
        "endpoint": result.get("endpoint", ""),
        "latency_ms": result.get("latency_ms"),
        "applied_photo_count": len(plans),
        "photo_count": len(plans),
        "message": _localized_text(raw_message, "外部 AI 已根据预览图判断场景并生成修图参数。")[:240],
    }
    return (
        AnalyzeResponse(
            batch_id=request.batch_id,
            style=request.style,
            scene=group_scene,
            aesthetic=aesthetic,
            edit_level=edit_level,
            user_suggestion=user_suggestion,
            ai_status=ai_status,
            group_style=GroupStyle(
                style=request.style,
                scene=group_scene,
                aesthetic=aesthetic,
                edit_level=edit_level,
                skin_tone_target=_skin_target(group_scene, aesthetic),
                contrast_level=_contrast_level(aesthetic),
                base_params=base_params,
            ),
            photos=plans,
        ),
        ai_status,
    )


def review_with_external_ai(request: ReviewRequest, config: AIConfig) -> tuple[ReviewResponse | None, dict[str, Any]]:
    metrics_by_photo = []
    for photo in request.photos:
        metrics_by_photo.append((photo, compare_metrics(photo.before_path, photo.after_path)))

    prompt = _review_prompt(request, metrics_by_photo)
    image_urls: list[str] = []
    for photo, _ in metrics_by_photo:
        before_url = _image_data_url(photo.before_path)
        after_url = _image_data_url(photo.after_path)
        if before_url:
            image_urls.append(before_url)
        if after_url:
            image_urls.append(after_url)

    result, used_images = _call_ai_with_image_fallback(config, prompt, image_urls, max_tokens=2400, timeout=90)
    if not result.get("passed"):
        return None, _fallback_status(config, result, str(result.get("message") or "外部 AI 审核调用失败。"))

    try:
        payload = _parse_json_object(str(result.get("text") or result.get("sample") or ""))
        results = _review_results_from_ai_payload(payload, metrics_by_photo)
    except ValueError as exc:
        return None, _fallback_status(config, result, f"外部 AI 审核结果不是有效 JSON：{exc}")

    if len(results) != len(metrics_by_photo):
        return None, _fallback_status(config, result, "外部 AI 没有为每张照片返回审核结果。")

    score = int(round(sum(item.score for item in results) / max(len(results), 1)))
    raw_message = str(payload.get("batch_notes") or payload.get("notes") or "")
    ai_status = {
        "mode": "external_ai_vision_review" if used_images else "external_ai_text_review",
        "requested_external_ai": True,
        "used_external_ai": True,
        "source": _provider_label(config),
        "provider": config.provider,
        "model": config.model,
        "wire_api": result.get("wire_api", config.wire_api),
        "endpoint": result.get("endpoint", ""),
        "latency_ms": result.get("latency_ms"),
        "message": _localized_text(raw_message, "外部 AI 已根据修图前后 proof 图完成审核。")[:240],
    }
    return (
        ReviewResponse(
            batch_id=request.batch_id,
            passed=all(item.passed for item in results),
            score=score,
            photos=results,
            ai_status=ai_status,
        ),
        ai_status,
    )


def _call_ai_with_image_fallback(
    config: AIConfig,
    prompt: str,
    image_urls: list[str],
    max_tokens: int,
    timeout: float,
) -> tuple[dict[str, Any], bool]:
    if image_urls:
        result = call_ai_text(config, prompt, max_tokens=max_tokens, timeout=timeout, image_urls=image_urls)
        if result.get("passed"):
            return result, True
        text_prompt = prompt.replace(
            "请以随请求附带的预览图作为主要依据，指标只作为辅助参考。",
            "当前没有可用的图片附件，请使用指标、元数据和用户风格作为主要依据。",
        ).replace(
            "请以每组修图前/修图后的图片对比作为主要依据，指标只作为辅助参考。",
            "当前没有可用的图片附件，请使用修图前后指标和当前参数作为主要依据。",
        )
        text_result = call_ai_text(config, text_prompt, max_tokens=max_tokens, timeout=timeout, image_urls=[])
        if text_result.get("passed"):
            text_result["image_fallback_message"] = result.get("message", "")
            return text_result, False
        return result, False
    return call_ai_text(config, prompt, max_tokens=max_tokens, timeout=timeout, image_urls=[]), False


def _analysis_prompt(
    request: AnalyzeRequest,
    metrics_by_photo: list[tuple[Any, dict[str, Any]]],
    resolved_scene: str,
    aesthetic: str,
    edit_level: str,
) -> str:
    photos = []
    photo_count = len(metrics_by_photo)
    batch_suggestion = clean_user_suggestion(request.user_suggestion)
    for index, (photo, metrics) in enumerate(metrics_by_photo, start=1):
        photos.append(
            {
                "image_order": index,
                "photo_id": photo.photo_id,
                "file_name": photo.file_name,
                "photo_user_suggestion": user_suggestion_for_photo(batch_suggestion, index - 1, photo_count),
                "metadata": photo.metadata.model_dump() if hasattr(photo.metadata, "model_dump") else {},
                "metrics": _public_metrics(metrics),
            }
        )
    payload = {
        "batch_id": request.batch_id,
        "requested_scene_hint": request.scene,
        "resolved_scene_hint": resolved_scene,
        "aesthetic": aesthetic,
        "edit_level": edit_level,
        "user_suggestion": batch_suggestion,
        "supported_scenes": sorted(SUPPORTED_SCENE_SET),
        "parameter_ranges": {
            "exposure": [-0.8, 0.8],
            "contrast": [-25, 30],
            "highlights": [-80, 20],
            "shadows": [-30, 60],
            "whites": [-30, 35],
            "blacks": [-35, 25],
            "temperature": [-900, 900],
            "tint": [-25, 25],
            "texture": [-30, 20],
            "clarity": [-25, 25],
            "dehaze": [-15, 20],
            "vibrance": [-15, 40],
            "saturation": [-20, 20],
            "sharpening": [0, 80],
            "noise_reduction": [0, 55],
        },
        "photos": photos,
    }
    return (
        "你是 Lightroom Classic 批量修图助手。请以随请求附带的预览图作为主要依据，指标只作为辅助参考。\n"
        "启用外部 AI 时，场景判断必须由你根据图片完成，不要沿用任何本地规则猜测。\n"
        "只返回严格 JSON，不要 Markdown，不要额外解释。每张照片必须返回：photo_id、scene、params、crop_suggestion、advanced_suggestions、notes。\n"
        "如果 user_suggestion 使用“第一张/第二张/图1/图2”描述不同要求，必须以每张 photos[].photo_user_suggestion 为准，不要把某一张的要求套到其他照片。\n"
        "scene 必须是 supported_scenes 中的英文值。params 是完整的 Lightroom 基础参数绝对值，必须包含所有 parameter_ranges 里的键。\n"
        "crop_suggestion 必须是 {enabled, aspect_ratio, crop:{left,top,right,bottom}, reason}。不需要裁剪时 enabled=false 且 crop 为 0,0,1,1。\n"
        "batch_notes、notes、reason、advanced_suggestions 必须使用中文。\n"
        "返回格式：{\"batch_notes\":\"中文说明\",\"group_scene\":\"grass_tree\",\"photos\":[{\"photo_id\":\"...\",\"scene\":\"grass_tree\",\"params\":{\"exposure\":0.05,...},\"crop_suggestion\":{\"enabled\":false,\"aspect_ratio\":\"原比例\",\"crop\":{\"left\":0,\"top\":0,\"right\":1,\"bottom\":1},\"reason\":\"中文原因\"},\"advanced_suggestions\":[\"中文建议\"],\"notes\":[\"中文说明\"]}]}。\n"
        f"数据：\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _review_prompt(request: ReviewRequest, metrics_by_photo: list[tuple[Any, dict[str, Any]]]) -> str:
    photos = []
    image_order = 1
    for photo, metrics in metrics_by_photo:
        photos.append(
            {
                "photo_id": photo.photo_id,
                "before_image_order": image_order,
                "after_image_order": image_order + 1,
                "current_params": photo.params,
                "metrics": _public_review_metrics(metrics),
            }
        )
        image_order += 2
    payload = {
        "batch_id": request.batch_id,
        "pass_index": request.pass_index,
        "aesthetic": request.aesthetic,
        "edit_level": request.edit_level,
        "user_suggestion": clean_user_suggestion(request.user_suggestion),
        "allowed_delta_params": PARAM_KEYS,
        "photos": photos,
    }
    return (
        "你是 Lightroom Classic 修图审核 AI。请以每组修图前/修图后的图片对比作为主要依据，指标只作为辅助参考。只返回严格 JSON。\n"
        "请为每张照片判断是否通过、给出 0-100 分、问题标签、以及用于改进当前参数的小幅 deltas。deltas 是相对修正量，不是最终参数。\n"
        "batch_notes 和 notes 必须使用中文；issues 可以使用简短英文标签或中文标签。\n"
        "返回格式：{\"passed\":true,\"score\":92,\"batch_notes\":\"中文审核总结\",\"photos\":[{\"photo_id\":\"...\",\"passed\":true,\"score\":92,\"issues\":[],\"deltas\":{\"exposure\":0.04},\"notes\":[\"中文说明\"]}]}。\n"
        f"数据：\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _plans_from_ai_payload(
    payload: dict[str, Any],
    metrics_by_photo: list[tuple[Any, dict[str, Any]]],
    aesthetic: str,
    edit_level: str,
    user_suggestion: str = "",
) -> list[PhotoPlan]:
    by_id = _items_by_photo_id(payload.get("photos"))
    plans: list[PhotoPlan] = []
    photo_count = len(metrics_by_photo)
    for index, (photo, metrics) in enumerate(metrics_by_photo):
        item = by_id.get(photo.photo_id)
        if not item:
            continue
        photo_suggestion = user_suggestion_for_photo(user_suggestion, index, photo_count)
        scene = _normalize_scene(str(item.get("scene") or item.get("detected_scene") or "auto"))
        params = _params_from_item(item)
        user_deltas = parameter_deltas_from_user_suggestion(photo_suggestion, scene)
        if user_deltas:
            params = apply_deltas(params, user_deltas).params
        crop = apply_crop_intent(_crop_from_item(item), photo_suggestion)
        local_analysis = analyze_local_regions(photo.preview_path, metrics, scene, aesthetic, user_suggestion=photo_suggestion)
        crop["reason"] = _localized_text(crop.get("reason"), _default_crop_reason(scene, crop))
        advanced_plan = _advanced_plan_from_item(item, crop, edit_level, photo_suggestion, scene, aesthetic)
        advanced_suggestions = user_suggestion_notes(photo_suggestion) + _localized_suggestions(_strings(item.get("advanced_suggestions")), scene, crop)
        lightroom_settings = to_lightroom_settings(params)
        lightroom_settings.update(_clean_lightroom_settings(advanced_plan.get("lightroom_settings", {})))
        plans.append(
            PhotoPlan(
                photo_id=photo.photo_id,
                file_name=photo.file_name,
                detected_scene=scene,
                ai_source="external_ai",
                ai_notes=_localized_notes(_notes_from_item(item), scene),
                params=params,
                lightroom_settings=lightroom_settings,
                metrics=metrics,
                local_analysis=local_analysis,
                crop_suggestion=crop,
                advanced_plan=advanced_plan,
                advanced_suggestions=advanced_suggestions,
            )
        )
    return plans


def _review_results_from_ai_payload(
    payload: dict[str, Any],
    metrics_by_photo: list[tuple[Any, dict[str, Any]]],
) -> list[ReviewResult]:
    by_id = _items_by_photo_id(payload.get("photos"))
    results: list[ReviewResult] = []
    for photo, metrics in metrics_by_photo:
        item = by_id.get(photo.photo_id)
        if not item:
            continue
        raw_deltas = _numeric_dict(item.get("deltas") if isinstance(item.get("deltas"), dict) else {})
        safe_deltas = clamp_deltas(raw_deltas)
        score = _bounded_int(item.get("score"), 0, 100, 85)
        passed = bool(item.get("passed", score >= 88))
        results.append(
            ReviewResult(
                photo_id=photo.photo_id,
                passed=passed,
                score=score,
                issues=_localized_issues(_strings(item.get("issues"))),
                deltas=safe_deltas,
                metrics=metrics,
                ai_source="external_ai",
                ai_notes=_localized_review_notes(_notes_from_item(item), passed, score, safe_deltas),
            )
        )
    return results


def _params_from_item(item: dict[str, Any]) -> dict[str, float | int]:
    params = item.get("params")
    if not isinstance(params, dict):
        params = item.get("lightroom_params")
    if not isinstance(params, dict):
        raise ValueError("photo item is missing params")
    clean = clamp_params(_numeric_dict(params))
    return clean


def _crop_from_item(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("crop_suggestion")
    if not isinstance(raw, dict):
        raw = item.get("crop") if isinstance(item.get("crop"), dict) else {}
    crop = raw.get("crop") if isinstance(raw.get("crop"), dict) else raw
    clean_crop = {
        "left": _bounded_float(crop.get("left"), 0.0, 1.0, 0.0) if isinstance(crop, dict) else 0.0,
        "top": _bounded_float(crop.get("top"), 0.0, 1.0, 0.0) if isinstance(crop, dict) else 0.0,
        "right": _bounded_float(crop.get("right"), 0.0, 1.0, 1.0) if isinstance(crop, dict) else 1.0,
        "bottom": _bounded_float(crop.get("bottom"), 0.0, 1.0, 1.0) if isinstance(crop, dict) else 1.0,
    }
    if clean_crop["right"] <= clean_crop["left"] or clean_crop["bottom"] <= clean_crop["top"]:
        clean_crop = {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
    enabled = bool(raw.get("enabled", False)) and clean_crop != {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
    return {
        "enabled": enabled,
        "mode": "ai",
        "aspect_ratio": str(raw.get("aspect_ratio") or raw.get("ratio") or "原比例"),
        "crop": clean_crop,
        "reason": str(raw.get("reason") or raw.get("notes") or "AI 构图/裁剪判断。"),
    }


def _advanced_plan_from_item(
    item: dict[str, Any],
    crop: dict[str, Any],
    edit_level: str,
    user_suggestion: str = "",
    scene: str = "auto",
    aesthetic: str = "natural",
) -> dict[str, Any]:
    raw = item.get("advanced_plan") if isinstance(item.get("advanced_plan"), dict) else {}
    settings = _clean_lightroom_settings(raw.get("lightroom_settings", {})) if edit_level == "basic_plus_advanced_execute" else {}
    suggestion_text = " ".join([user_suggestion, *_strings(item.get("advanced_suggestions"))])
    vignette_settings = vignette_lightroom_settings(parse_user_intent(suggestion_text), scene, aesthetic)
    if edit_level == "basic_plus_advanced_execute" and vignette_settings:
        settings.update(vignette_settings)
    crop_settings = crop_lightroom_settings(crop)
    if crop_settings:
        settings.update(crop_settings)
    applied = bool(settings)
    sections = raw.get("sections") if isinstance(raw.get("sections"), list) else []
    sections = [_localized_section(item) for item in sections if isinstance(item, dict)]
    if vignette_settings:
        sections = list(sections) + [{"name": "暗角/主体突出", "applied": applied, "settings": vignette_settings}]
    if crop_settings:
        sections = list(sections) + [{"name": "AI 构图/裁剪", "applied": applied, "settings": crop_settings}]
    return {
        "applied": applied,
        "lightroom_settings": settings if applied else {},
        "sections": sections,
        "limitations": _localized_generic_list(_strings(raw.get("limitations")), "进阶修改受 Lightroom SDK 可控参数限制，已记录为可执行范围内的调整。"),
    }


def _clean_lightroom_settings(settings: Any) -> dict[str, Any]:
    if not isinstance(settings, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in settings.items():
        key = str(key)
        if not key or len(key) > 80:
            continue
        if isinstance(value, bool):
            clean[key] = value
        elif isinstance(value, (int, float, str)):
            clean[key] = value
    return clean


def _public_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "width",
        "height",
        "avg_luma",
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
    return {key: metrics[key] for key in keys if key in metrics}


def _public_review_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "before": _public_metrics(metrics.get("before", {})),
        "after": _public_metrics(metrics.get("after", {})),
        "delta": metrics.get("delta", {}),
    }


def _parse_json_object(text: str) -> dict[str, Any]:
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
    raise ValueError("no JSON object found")


def _image_data_url(path: str | Path) -> str:
    try:
        image = Image.open(path).convert("RGB")
        image.thumbnail((512, 512))
        handle = io.BytesIO()
        image.save(handle, format="JPEG", quality=72)
    except OSError:
        return ""
    encoded = base64.b64encode(handle.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _items_by_photo_id(items: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and item.get("photo_id"):
            result[str(item["photo_id"])] = item
    return result


def _numeric_dict(values: dict[str, Any]) -> dict[str, float]:
    clean: dict[str, float] = {}
    for key, value in values.items():
        if key not in PARAM_KEYS:
            continue
        try:
            clean[key] = float(value)
        except (TypeError, ValueError):
            continue
    return clean


def _strings(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()[:240]]
    if isinstance(value, list):
        return [str(item).strip()[:240] for item in value if str(item).strip()][:6]
    return []


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _localized_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    exact = {
        "AI crop/recompose": "AI 构图/裁剪",
        "original": "原比例",
    }
    if text in exact:
        return exact[text]
    return text[:240] if _contains_cjk(text) else fallback


def _localized_generic_list(items: list[str], fallback: str) -> list[str]:
    chinese = [item for item in items if _contains_cjk(item)]
    return chinese[:6] if chinese else [fallback]


def _scene_name(scene: str) -> str:
    return SCENE_NAMES.get(scene, "当前照片")


def _localized_notes(notes: list[str], scene: str) -> list[str]:
    chinese = [item for item in notes if _contains_cjk(item)]
    if chinese:
        return chinese[:6]
    result = [
        f"外部 AI 根据预览图判断为{_scene_name(scene)}场景。",
        "已根据画面亮度、色彩和细节生成 Lightroom 基础参数。",
    ]
    if scene not in PORTRAIT_SCENES:
        result.append("该照片未按人像或人脸规则处理，优先保持场景真实质感。")
    return result


def _localized_review_notes(notes: list[str], passed: bool, score: int, deltas: dict[str, Any]) -> list[str]:
    chinese = [item for item in notes if _contains_cjk(item)]
    if chinese:
        return chinese[:6]
    state = "通过" if passed else "需要继续微调"
    result = [f"外部 AI 审核判定为{state}，评分 {score}。"]
    if deltas:
        result.append("已根据修图前后 proof 图给出二次修正量。")
    else:
        result.append("当前效果没有明显需要追加的参数修正。")
    return result


def _localized_suggestions(items: list[str], scene: str, crop: dict[str, Any]) -> list[str]:
    chinese = [item for item in items if _contains_cjk(item)]
    if chinese:
        return chinese[:6]
    suggestions: list[str] = []
    if crop.get("enabled"):
        suggestions.append("已将裁剪/重构图作为进阶执行项，用于强化主体并减少边缘干扰。")
    if scene in PORTRAIT_SCENES:
        suggestions.append("如需要进阶精修，可用人像或面部蒙版轻微提亮肤色并控制皮肤纹理。")
    elif scene in NATURE_SCENES:
        suggestions.append("如需要进阶精修，可用线性或径向蒙版控制天空、高光、前景和背景层次。")
    elif scene == "architecture":
        suggestions.append("如需要进阶精修，可配合垂直校正和局部清晰度控制建筑线条。")
    else:
        suggestions.append("如需要进阶精修，可用局部蒙版微调主体亮度、背景层次和色彩分离。")
    suggestions.append("可在 Lightroom 中继续手动微调蒙版、混色器和局部细节。")
    return suggestions[:3]


def _default_crop_reason(scene: str, crop: dict[str, Any]) -> str:
    if crop.get("enabled"):
        return f"AI 建议裁剪以强化{_scene_name(scene)}主体，并减少画面边缘干扰。"
    return f"AI 判断当前{_scene_name(scene)}构图可以保留原比例。"


def _localized_section(section: dict[str, Any]) -> dict[str, Any]:
    clean = dict(section)
    clean["name"] = _localized_text(clean.get("name"), "AI 进阶调整")
    if "notes" in clean:
        clean["notes"] = _localized_generic_list(_strings(clean.get("notes")), "AI 已记录该项进阶调整。")
    return clean


def _localized_issues(issues: list[str]) -> list[str]:
    result: list[str] = []
    for issue in issues:
        text = str(issue).strip()
        if not text:
            continue
        key = text.lower().replace(" ", "_").replace("-", "_")
        if key in ISSUE_ALIASES:
            result.append(ISSUE_ALIASES[key])
        elif _contains_cjk(text):
            result.append(text[:80])
        else:
            result.append("needs_minor_tuning")
    unique: list[str] = []
    for issue in result:
        if issue not in unique:
            unique.append(issue)
    return unique[:6]


def _notes_from_item(item: dict[str, Any]) -> list[str]:
    notes = _strings(item.get("notes"))
    for key in ("reason", "comment"):
        notes.extend(_strings(item.get(key)))
    return notes[:6]


def _normalize_scene(value: str) -> str:
    clean = value.strip()
    return clean if clean in SUPPORTED_SCENE_SET else "auto"


def _group_scene(payload: dict[str, Any], plans: list[PhotoPlan], fallback: str) -> str:
    scene = _normalize_scene(str(payload.get("group_scene") or payload.get("scene") or ""))
    if scene != "auto":
        return scene
    counts = Counter(plan.detected_scene for plan in plans if plan.detected_scene != "auto")
    if counts:
        return counts.most_common(1)[0][0]
    return fallback if fallback in SUPPORTED_SCENE_SET else "auto"


def _average_params(param_sets: list[dict[str, Any]]) -> dict[str, float | int]:
    if not param_sets:
        return clamp_params(DEFAULT_PARAMS)
    totals = {key: 0.0 for key in PARAM_KEYS}
    for params in param_sets:
        clean = clamp_params(_numeric_dict(params))
        for key in PARAM_KEYS:
            totals[key] += float(clean[key])
    return clamp_params({key: value / len(param_sets) for key, value in totals.items()})


def _bounded_float(value: Any, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return round(min(max(number, low), high), 4)


def _bounded_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return min(max(number, low), high)


def _fallback_status(config: AIConfig, result: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "mode": "rules_fallback",
        "requested_external_ai": True,
        "used_external_ai": False,
        "source": "rules",
        "external_source": _provider_label(config),
        "provider": config.provider,
        "model": config.model,
        "wire_api": result.get("wire_api", config.wire_api),
        "endpoint": result.get("endpoint", ""),
        "latency_ms": result.get("latency_ms"),
        "message": message[:300],
    }


def _provider_label(config: AIConfig) -> str:
    if config.provider == "openai_relay":
        return "中转站 API"
    if config.provider == "openai_compatible":
        return "OpenAI 兼容接口"
    if config.provider == "custom":
        return "自定义接口"
    return "本地规则"


def _skin_target(scene: str, aesthetic: str) -> str:
    if scene in {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}:
        if aesthetic in {"sweet", "warm_soft", "commercial_clean"}:
            return "warm_clean"
        if aesthetic in {"texture", "master", "high_gray"}:
            return "neutral_texture"
        return "warm_neutral"
    return "not_primary"


def _contrast_level(aesthetic: str) -> str:
    if aesthetic in {"sweet", "japanese_clear", "warm_soft", "high_gray"}:
        return "soft"
    if aesthetic in {"texture", "master", "landscape"}:
        return "strong"
    return "natural"
