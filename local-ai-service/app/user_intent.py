from __future__ import annotations

import re
from typing import Any


MAX_USER_SUGGESTION_CHARS = 800

PORTRAIT_SCENES = {"portrait", "wedding", "children", "indoor_portrait", "outdoor_backlight"}
LANDSCAPE_SCENES = {"landscape", "blue_sky", "sunset", "grass_tree", "forest", "architecture", "night"}
ORDINAL_WORDS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
PHOTO_MARKER_RE = re.compile(
    r"(?:第\s*(?P<cn>[一二两三四五六七八九十]+|\d+)\s*(?:张|幅|个|张图|照片|图)|(?:图|照片)\s*(?P<num>\d+)|(?P<num2>\d+)\s*[\.、)])"
)


def clean_user_suggestion(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:MAX_USER_SUGGESTION_CHARS]


def user_suggestion_for_photo(value: Any, photo_index: int, photo_count: int) -> str:
    parts = split_user_suggestion_by_photo(value, photo_count)
    if 0 <= photo_index < len(parts):
        return parts[photo_index]
    return clean_user_suggestion(value)


def split_user_suggestion_by_photo(value: Any, photo_count: int) -> list[str]:
    text = clean_user_suggestion(value)
    if photo_count <= 0:
        return []
    if not text:
        return [""] * photo_count

    matches = list(PHOTO_MARKER_RE.finditer(text))
    if not matches:
        return [text] * photo_count

    global_prefix = _clean_segment(text[: matches[0].start()])
    result = [""] * photo_count
    for index, match in enumerate(matches):
        photo_number = _marker_number(match)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = _clean_segment(text[start:end])
        if photo_number is None or not (1 <= photo_number <= photo_count):
            continue
        result[photo_number - 1] = _join_suggestion_parts(global_prefix, segment)

    return [item or global_prefix for item in result]


def parse_user_intent(value: Any) -> dict[str, bool]:
    text = clean_user_suggestion(value).lower()
    return {
        "has_suggestion": bool(text),
        "keep_original_ratio": _has_any(
            text,
            [
                "保持原比例",
                "保留原比例",
                "原比例",
                "不要裁剪",
                "不裁剪",
                "不要裁切",
                "不裁切",
                "不改变比例",
                "保持这个比例",
                "keep ratio",
                "original ratio",
                "no crop",
                "do not crop",
            ],
        ),
        "avoid_face_slimming": _has_any(
            text,
            ["不要瘦脸", "不瘦脸", "别瘦脸", "不要液化", "不液化", "no face slimming", "no slimming"],
        ),
        "avoid_skin_smoothing": _has_any(
            text,
            ["不要磨皮", "不磨皮", "别磨皮", "保留皮肤纹理", "保留肤质", "no skin smoothing", "no smoothing"],
        ),
        "skin_cleanup": _has_any(text, ["去瑕疵", "去除瑕疵", "修瑕疵", "痘", "斑", "blemish", "acne"]),
        "focus_face": _has_any(text, ["重点修脸", "重点调整脸", "脸部", "面部", "人脸", "face"]),
        "landscape_light": _has_any(text, ["增加光影", "加强光影", "光影", "层次", "dodge", "burn", "light and shadow"]),
        "sky_focus": _has_any(text, ["天空", "蓝天", "云", "sky", "cloud"]),
        "foliage_green_boost": _has_any(
            text,
            ["草地加上蒙版", "草地蒙版", "草地更绿", "让其更绿", "让草地更绿", "更绿", "绿一点", "绿一些", "增加绿色"],
        ),
        "avoid_foliage_green_boost": _has_any(text, ["不要太绿", "别太绿", "降低绿色", "压绿色", "绿色不要太抢"]),
        "lower_exposure": _has_any(text, ["曝光低一点", "曝光低一些", "压低曝光", "降低曝光", "曝光暗一点", "整体暗一点"]),
        "darken_architecture": _has_any(
            text,
            ["压低建筑物", "压低建筑", "建筑物曝光", "建筑曝光", "建筑暗一点", "压暗建筑", "压暗建筑物"],
        ),
        "subject_focus": _has_any(text, ["突出人物主体", "突出主体", "突出人物", "强化主体", "主体突出", "人物主体", "subject"]),
        "vignette": _has_any(text, ["暗角", "加上暗角", "加暗角", "四周加暗", "四周压暗", "压暗四周", "边缘压暗", "vignette"]),
        "avoid_vignette": _has_any(text, ["不要暗角", "不加暗角", "别加暗角", "去掉暗角", "no vignette"]),
        "natural": _has_any(text, ["自然", "克制", "不要过度", "别太重", "轻微", "natural", "subtle"]),
        "keep_dark": _has_any(text, ["保留暗调", "保持暗调", "不要太亮", "暗调", "low key"]),
    }


def apply_crop_intent(crop: dict[str, Any], value: Any) -> dict[str, Any]:
    intent = parse_user_intent(value)
    if not intent["keep_original_ratio"]:
        return crop
    updated = dict(crop or {})
    updated.update(
        {
            "enabled": False,
            "mode": "user_suggestion",
            "aspect_ratio": "原比例",
            "crop": {"left": 0, "top": 0, "right": 1, "bottom": 1},
            "reason": "已按用户建议保持原比例，不自动裁剪。",
        }
    )
    return updated


def apply_operation_intent(
    operations: list[dict[str, Any]],
    value: Any,
    regions: list[dict[str, Any]] | None = None,
    scene: str = "auto",
) -> list[dict[str, Any]]:
    intent = parse_user_intent(value)
    if not intent["has_suggestion"]:
        return operations

    filtered: list[dict[str, Any]] = []
    for operation in operations:
        operation_id = str(operation.get("id") or "")
        if intent["avoid_face_slimming"] and operation_id == "face_slimming":
            continue
        if intent["avoid_skin_smoothing"] and operation_id == "skin_texture_smoothing":
            continue
        item = dict(operation)
        if intent["natural"]:
            item["strength"] = round(min(float(item.get("strength", 0.18)), 0.18), 3)
        filtered.append(item)

    region_ids = _region_ids(regions or [])
    if intent["skin_cleanup"] and ("skin" in region_ids or "face" in region_ids or scene in PORTRAIT_SCENES):
        _append_operation(
            filtered,
            "skin_cleanup",
            "pixel",
            "skin" if "skin" in region_ids else "face",
            "Prioritize user-requested conservative skin blemish cleanup.",
            0.2 if intent["natural"] else 0.24,
            True,
        )
    if (intent["focus_face"] or intent["subject_focus"]) and "face" in region_ids:
        _append_operation(
            filtered,
            "face_relight",
            "pixel",
            "face",
            "Prioritize user-requested facial tone and local light refinement.",
            0.16 if intent["natural"] else 0.2,
            False,
        )
    if (intent["landscape_light"] or intent["subject_focus"]) and (
        scene in LANDSCAPE_SCENES or {"foreground", "center_subject", "subject"} & region_ids
    ):
        region_id = "foreground" if "foreground" in region_ids else ("subject" if "subject" in region_ids else "center_subject")
        _append_operation(
            filtered,
            "landscape_dodge_burn",
            "pixel",
            region_id,
            "Prioritize user-requested restrained local light and shadow depth.",
            0.18 if intent["natural"] else 0.24,
            False,
        )
    if intent["sky_focus"] and "sky" in region_ids:
        _append_operation(
            filtered,
            "sky_light_balance",
            "pixel",
            "sky",
            "Prioritize user-requested sky highlight and tonal separation.",
            0.18 if intent["natural"] else 0.24,
            False,
        )
    if intent["darken_architecture"] and (
        "foreground" in region_ids or "center_subject" in region_ids or "shadows" in region_ids or scene in LANDSCAPE_SCENES
    ):
        region_id = "foreground" if "foreground" in region_ids else ("center_subject" if "center_subject" in region_ids else "shadows")
        _append_operation(
            filtered,
            "architecture_darken",
            "pixel",
            region_id,
            "Prioritize user-requested masked architecture exposure reduction.",
            0.16 if intent["natural"] else 0.22,
            False,
        )
    if intent["foliage_green_boost"] and not intent["avoid_foliage_green_boost"] and (
        "foliage" in region_ids or scene in {"grass_tree", "forest", "landscape", "portrait", "wedding"}
    ):
        _append_operation(
            filtered,
            "foliage_green_boost",
            "pixel",
            "foliage" if "foliage" in region_ids else "center_subject",
            "Prioritize user-requested grass/foliage mask and greener tone.",
            0.18 if intent["natural"] else 0.24,
            False,
        )

    return filtered


def filter_operation_ids(operation_ids: list[str], value: Any) -> list[str]:
    intent = parse_user_intent(value)
    if not intent["has_suggestion"]:
        return operation_ids
    result: list[str] = []
    for operation_id in operation_ids:
        if intent["avoid_face_slimming"] and operation_id == "face_slimming":
            continue
        if intent["avoid_skin_smoothing"] and operation_id == "skin_texture_smoothing":
            continue
        result.append(operation_id)
    return result


def adjusted_pixel_strength(strength: float, value: Any) -> float:
    intent = parse_user_intent(value)
    if intent["natural"] or intent["keep_dark"]:
        return strength * 0.78
    return strength


def parameter_deltas_from_user_suggestion(value: Any, scene: str = "auto") -> dict[str, float]:
    intent = parse_user_intent(value)
    deltas: dict[str, float] = {}
    if intent["lower_exposure"]:
        deltas["exposure"] = deltas.get("exposure", 0) - 0.12
        deltas["highlights"] = deltas.get("highlights", 0) - 4
    if intent["darken_architecture"]:
        deltas["exposure"] = deltas.get("exposure", 0) - 0.08
        deltas["shadows"] = deltas.get("shadows", 0) - 6
        deltas["blacks"] = deltas.get("blacks", 0) - 5
    if intent["sky_focus"] and scene in LANDSCAPE_SCENES:
        deltas["highlights"] = deltas.get("highlights", 0) - 6
        deltas["dehaze"] = deltas.get("dehaze", 0) + 3
        deltas["vibrance"] = deltas.get("vibrance", 0) + 2
    return deltas


def user_suggestion_notes(value: Any) -> list[str]:
    suggestion = clean_user_suggestion(value)
    if not suggestion:
        return []
    notes = [f"已收到用户修图建议：{suggestion}"]
    intent = parse_user_intent(suggestion)
    if intent["keep_original_ratio"]:
        notes.append("本批次会优先保持原比例，不自动裁剪。")
    if intent["avoid_face_slimming"]:
        notes.append("本批次会跳过自动瘦脸/液化类像素操作。")
    if intent["avoid_skin_smoothing"]:
        notes.append("本批次会保留皮肤纹理，跳过自动磨皮。")
    if intent["vignette"] and not intent["avoid_vignette"]:
        notes.append("本批次会加入克制暗角，用于压暗边缘并突出主体。")
    if intent["foliage_green_boost"] and not intent["avoid_foliage_green_boost"]:
        notes.append("本张会优先增强草地/绿植区域，让绿色更明确。")
    if intent["lower_exposure"]:
        notes.append("本张会按建议轻微降低整体曝光。")
    if intent["darken_architecture"]:
        notes.append("本张会优先压低建筑或暗部区域，保留天空表现。")
    return notes[:4]


def _clean_segment(value: str) -> str:
    return value.strip(" \t\r\n,，.。;；:：、")


def _join_suggestion_parts(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def _marker_number(match: re.Match[str]) -> int | None:
    raw = match.group("cn") or match.group("num") or match.group("num2") or ""
    raw = raw.strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if raw in ORDINAL_WORDS:
        return ORDINAL_WORDS[raw]
    if raw.startswith("十") and len(raw) == 2:
        return 10 + ORDINAL_WORDS.get(raw[1], 0)
    if raw.endswith("十") and len(raw) == 2:
        return ORDINAL_WORDS.get(raw[0], 0) * 10
    if "十" in raw:
        left, right = raw.split("十", 1)
        return ORDINAL_WORDS.get(left, 1) * 10 + ORDINAL_WORDS.get(right, 0)
    return None


def _has_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _region_ids(regions: list[dict[str, Any]]) -> set[str]:
    return {str(region.get("id") or "") for region in regions}


def _append_operation(
    operations: list[dict[str, Any]],
    operation_id: str,
    target: str,
    region_id: str,
    description: str,
    strength: float,
    requires_review: bool,
) -> None:
    if any(str(item.get("id") or "") == operation_id for item in operations):
        return
    operations.append(
        {
            "id": operation_id,
            "target": target,
            "region_id": region_id,
            "status": "ready_for_pixel_endpoint",
            "strength": round(strength, 3),
            "requires_review": requires_review,
            "description": description,
        }
    )
