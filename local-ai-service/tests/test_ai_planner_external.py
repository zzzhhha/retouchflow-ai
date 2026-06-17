import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.ai_planner import Planner
from app.config import AIConfig
from app.dashboard import _ai_source_summary
from app.review import Reviewer
from app.schemas import AnalyzePhoto, AnalyzeRequest, ReviewPhoto, ReviewRequest


def _preview(path: Path, color: tuple[int, int, int] = (90, 150, 90)) -> str:
    Image.new("RGB", (120, 80), color).save(path)
    return str(path)


def _request(preview_path: str) -> AnalyzeRequest:
    return AnalyzeRequest(
        batch_id="external-ai-test",
        style="natural_portrait",
        scene="auto",
        aesthetic="natural",
        edit_level="basic",
        photos=[
            AnalyzePhoto(
                photo_id="p1",
                file_name="sample.jpg",
                preview_path=preview_path,
            )
        ],
    )


def _external_config() -> AIConfig:
    return AIConfig(
        provider="openai_relay",
        api_key="sk-test-secret",
        base_url="https://relay.example.com/v1",
        model="relay-model",
        wire_api="openai_relay",
        enabled=True,
    )


class ExternalAIPlannerTests(unittest.TestCase):
    def test_enabled_external_ai_is_used_for_planning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            request = _request(_preview(Path(temp_dir) / "sample.jpg"))
            ai_text = json.dumps(
                {
                    "batch_notes": "External AI used the preview image as source of truth.",
                    "group_scene": "landscape",
                    "photos": [
                        {
                            "photo_id": "p1",
                            "scene": "landscape",
                            "params": {
                                "exposure": 0.1,
                                "contrast": 8,
                                "highlights": -24,
                                "shadows": 14,
                                "whites": 4,
                                "blacks": -8,
                                "temperature": -60,
                                "tint": 0,
                                "texture": 8,
                                "clarity": 6,
                                "dehaze": 4,
                                "vibrance": 12,
                                "saturation": -2,
                                "sharpening": 42,
                                "noise_reduction": 12,
                            },
                            "crop_suggestion": {
                                "enabled": False,
                                "aspect_ratio": "original",
                                "crop": {"left": 0, "top": 0, "right": 1, "bottom": 1},
                                "reason": "No crop needed.",
                            },
                            "notes": "Landscape image, not portrait.",
                        }
                    ],
                },
                ensure_ascii=False,
            )

            with patch("app.ai_planner.load_ai_config", return_value=_external_config()), patch(
                "app.external_ai.call_ai_text",
                return_value={
                    "passed": True,
                    "text": ai_text,
                    "wire_api": "chat_completions",
                    "endpoint": "https://relay.example.com/v1/chat/completions",
                    "latency_ms": 20,
                },
            ) as call_ai:
                response = Planner().analyze(request)

        self.assertTrue(call_ai.called)
        self.assertTrue(response.ai_status["used_external_ai"])
        self.assertEqual(response.ai_status["source"], "中转站 API")
        self.assertEqual(response.ai_status["wire_api"], "chat_completions")
        self.assertEqual(response.photos[0].ai_source, "external_ai")
        self.assertEqual(response.photos[0].detected_scene, "landscape")
        self.assertTrue(any("风景" in note for note in response.photos[0].ai_notes))
        self.assertTrue(all("not portrait" not in note for note in response.photos[0].ai_notes))
        self.assertEqual(response.photos[0].crop_suggestion["reason"], "AI 判断当前风景构图可以保留原比例。")

    def test_external_ai_failure_falls_back_to_rules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            request = _request(_preview(Path(temp_dir) / "sample.jpg"))

            with patch("app.ai_planner.load_ai_config", return_value=_external_config()), patch(
                "app.external_ai.call_ai_text",
                return_value={
                    "passed": False,
                    "message": "HTTP 403",
                    "wire_api": "chat_completions",
                    "endpoint": "https://relay.example.com/v1/chat/completions",
                },
            ):
                response = Planner().analyze(request)

        self.assertEqual(response.ai_status["mode"], "rules_fallback")
        self.assertFalse(response.ai_status["used_external_ai"])
        self.assertEqual(response.photos[0].ai_source, "rules")
        self.assertIn("HTTP 403", response.ai_status["message"])

    def test_external_ai_vignette_suggestion_becomes_executable_setting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            request = AnalyzeRequest(
                batch_id="external-vignette-test",
                style="natural_portrait",
                scene="portrait",
                aesthetic="natural",
                edit_level="basic_plus_advanced_execute",
                user_suggestion="突出人物主体，四周加上暗角",
                photos=[
                    AnalyzePhoto(
                        photo_id="p1",
                        file_name="portrait.jpg",
                        preview_path=_preview(Path(temp_dir) / "portrait.jpg", (120, 100, 90)),
                    )
                ],
            )
            ai_text = json.dumps(
                {
                    "batch_notes": "按用户建议突出人物主体并加暗角。",
                    "group_scene": "portrait",
                    "photos": [
                        {
                            "photo_id": "p1",
                            "scene": "portrait",
                            "params": {
                                "exposure": 0.1,
                                "contrast": 6,
                                "highlights": -18,
                                "shadows": 16,
                                "whites": 4,
                                "blacks": -6,
                                "temperature": 0,
                                "tint": 0,
                                "texture": -6,
                                "clarity": -3,
                                "dehaze": 0,
                                "vibrance": 8,
                                "saturation": -2,
                                "sharpening": 32,
                                "noise_reduction": 16,
                            },
                            "crop_suggestion": {
                                "enabled": False,
                                "aspect_ratio": "original",
                                "crop": {"left": 0, "top": 0, "right": 1, "bottom": 1},
                                "reason": "保持原构图。",
                            },
                            "advanced_suggestions": ["添加轻中度暗角突出人物主体。"],
                            "notes": ["人像主体需要更突出。"],
                        }
                    ],
                },
                ensure_ascii=False,
            )

            with patch("app.ai_planner.load_ai_config", return_value=_external_config()), patch(
                "app.external_ai.call_ai_text",
                return_value={"passed": True, "text": ai_text, "wire_api": "responses", "latency_ms": 20},
            ):
                response = Planner().analyze(request)

        settings = response.photos[0].advanced_plan["lightroom_settings"]
        self.assertIn("PostCropVignetteAmount", settings)
        self.assertLess(settings["PostCropVignetteAmount"], 0)
        self.assertIn("PostCropVignetteAmount", response.photos[0].lightroom_settings)

    def test_recent_batch_ai_source_label_mentions_fallback(self):
        self.assertEqual(
            _ai_source_summary({"requested_external_ai": True, "used_external_ai": False}),
            "外部 AI 失败，规则回退",
        )
        self.assertIn(
            "中转站 API",
            _ai_source_summary(
                {
                    "used_external_ai": True,
                    "source": "中转站 API",
                    "wire_api": "chat_completions",
                    "model": "relay-model",
                }
            ),
        )

    def test_enabled_external_ai_is_used_for_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            before_path = _preview(Path(temp_dir) / "before.jpg", (90, 120, 90))
            after_path = _preview(Path(temp_dir) / "after.jpg", (110, 135, 105))
            request = ReviewRequest(
                batch_id="external-review-test",
                pass_index=1,
                photos=[
                    ReviewPhoto(
                        photo_id="p1",
                        before_path=before_path,
                        after_path=after_path,
                        params={"exposure": 0.1, "highlights": -10},
                    )
                ],
            )
            ai_text = json.dumps(
                {
                    "passed": False,
                    "score": 84,
                    "batch_notes": "External AI reviewed before/after proof images.",
                    "photos": [
                        {
                            "photo_id": "p1",
                            "passed": False,
                            "score": 84,
                            "issues": ["slightly_dark"],
                            "deltas": {"exposure": 0.05, "shadows": 4},
                            "notes": ["Needs a small lift."],
                        }
                    ],
                },
                ensure_ascii=False,
            )

            with patch("app.review.load_ai_config", return_value=_external_config()), patch(
                "app.external_ai.call_ai_text",
                return_value={
                    "passed": True,
                    "text": ai_text,
                    "wire_api": "responses",
                    "endpoint": "https://relay.example.com/v1/responses",
                    "latency_ms": 30,
                },
            ) as call_ai:
                response = Reviewer().review(request)

        self.assertTrue(call_ai.called)
        self.assertTrue(response.ai_status["used_external_ai"])
        self.assertEqual(response.photos[0].ai_source, "external_ai")
        self.assertEqual(response.photos[0].score, 84)
        self.assertEqual(response.photos[0].deltas["exposure"], 0.05)
        self.assertEqual(response.photos[0].issues, ["needs_minor_tuning"])
        self.assertTrue(any("评分 84" in note for note in response.photos[0].ai_notes))


if __name__ == "__main__":
    unittest.main()
