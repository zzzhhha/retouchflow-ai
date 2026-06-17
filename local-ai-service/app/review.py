from __future__ import annotations

from typing import Any

from .config import load_ai_config
from .external_ai import external_ai_enabled, review_with_external_ai
from .image_metrics import compare_metrics
from .lightroom_params import apply_deltas, clamp_deltas
from .schemas import ReviewRequest, ReviewResponse, ReviewResult


class Reviewer:
    def review(self, request: ReviewRequest) -> ReviewResponse:
        config = load_ai_config()
        external_fallback_status: dict[str, Any] | None = None
        if external_ai_enabled(config):
            external_response, external_fallback_status = review_with_external_ai(request, config)
            if external_response is not None:
                return external_response

        results: list[ReviewResult] = []
        for photo in request.photos:
            metrics = compare_metrics(photo.before_path, photo.after_path)
            score, issues, deltas = self._score(metrics)
            safe_plan = apply_deltas(photo.params, deltas)
            safe_deltas = {
                key: safe_plan.params[key] - float(photo.params.get(key, 0))
                for key in clamp_deltas(deltas)
                if key in safe_plan.params
            }
            results.append(
                ReviewResult(
                    photo_id=photo.photo_id,
                    passed=score >= 88,
                    score=score,
                    issues=issues,
                    deltas=clamp_deltas(safe_deltas),
                    metrics=metrics,
                )
            )

        batch_score = int(round(sum(result.score for result in results) / max(len(results), 1)))
        return ReviewResponse(
            batch_id=request.batch_id,
            passed=all(result.passed for result in results),
            score=batch_score,
            photos=results,
            ai_status=external_fallback_status
            or {
                "mode": "rules_review",
                "requested_external_ai": False,
                "used_external_ai": False,
                "source": "rules",
                "message": "外部 AI 未启用，使用本地审核规则评分。",
            },
        )

    def _score(self, metrics: dict[str, Any]) -> tuple[int, list[str], dict[str, float]]:
        after = metrics["after"]
        issues: list[str] = []
        deltas: dict[str, float] = {}
        score = 100

        avg_luma = float(after["avg_luma"])
        highlight_clip = float(after["highlight_clip"])
        shadow_clip = float(after["shadow_clip"])
        saturation = float(after["avg_saturation"])
        warmth = float(after["warmth"])

        if avg_luma < 105:
            issues.append("too_dark")
            deltas["exposure"] = deltas.get("exposure", 0) + 0.08
            deltas["shadows"] = deltas.get("shadows", 0) + 6
            score -= min(18, int((105 - avg_luma) / 2))
        elif avg_luma > 165:
            issues.append("too_bright")
            deltas["exposure"] = deltas.get("exposure", 0) - 0.08
            deltas["highlights"] = deltas.get("highlights", 0) - 6
            score -= min(18, int((avg_luma - 165) / 2))

        if highlight_clip > 0.025:
            issues.append("highlights_clipped")
            deltas["highlights"] = deltas.get("highlights", 0) - 10
            deltas["whites"] = deltas.get("whites", 0) - 5
            score -= min(14, int(highlight_clip * 300))

        if shadow_clip > 0.04:
            issues.append("shadows_blocked")
            deltas["shadows"] = deltas.get("shadows", 0) + 8
            deltas["blacks"] = deltas.get("blacks", 0) + 4
            score -= min(10, int(shadow_clip * 180))

        if saturation > 78:
            issues.append("over_saturated")
            deltas["vibrance"] = deltas.get("vibrance", 0) - 5
            deltas["saturation"] = deltas.get("saturation", 0) - 3
            score -= min(10, int((saturation - 78) / 2))

        if warmth > 55:
            issues.append("too_warm")
            deltas["temperature"] = deltas.get("temperature", 0) - 180
            score -= min(8, int((warmth - 55) / 8))
        elif warmth < -55:
            issues.append("too_cool")
            deltas["temperature"] = deltas.get("temperature", 0) + 180
            score -= min(8, int((-55 - warmth) / 8))

        return max(0, min(100, score)), issues, deltas
