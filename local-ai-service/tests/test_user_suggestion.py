import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.advanced_edits import build_advanced_plan
from app.ai_planner import Planner
from app.config import AIConfig
from app.external_ai import _analysis_prompt
from app.image_metrics import image_metrics
from app.local_regions import analyze_local_regions
from app.pixel_retouch import render_pixel_retouch
from app.schemas import AnalyzePhoto, AnalyzeRequest
from app.user_intent import (
    apply_crop_intent,
    parameter_deltas_from_user_suggestion,
    parse_user_intent,
    split_user_suggestion_by_photo,
)
from unittest.mock import patch


def _portrait(path: Path) -> str:
    image = Image.new("RGB", (180, 220), (76, 78, 82))
    draw = ImageDraw.Draw(image)
    draw.ellipse((54, 42, 126, 132), fill=(196, 132, 96))
    draw.rectangle((74, 126, 108, 190), fill=(184, 118, 88))
    draw.ellipse((82, 80, 88, 86), fill=(95, 56, 50))
    image.save(path)
    return str(path)


class UserSuggestionTests(unittest.TestCase):
    def test_keep_original_ratio_overrides_crop(self):
        crop = {
            "enabled": True,
            "mode": "suggestion",
            "aspect_ratio": "4:5",
            "crop": {"left": 0.1, "top": 0, "right": 0.9, "bottom": 1},
            "reason": "rule crop",
        }

        updated = apply_crop_intent(crop, "保持原比例，不要裁剪")

        self.assertFalse(updated["enabled"])
        self.assertEqual(updated["aspect_ratio"], "原比例")
        self.assertEqual(updated["crop"], {"left": 0, "top": 0, "right": 1, "bottom": 1})

    def test_local_regions_respect_negative_portrait_operations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = _portrait(Path(temp_dir) / "portrait.jpg")
            metrics = image_metrics(path)
            analysis = analyze_local_regions(
                path,
                metrics,
                "portrait",
                "natural",
                user_suggestion="不要瘦脸，不要磨皮，只去瑕疵",
            )

        operation_ids = {item["id"] for item in analysis["operations"]}
        self.assertIn("skin_cleanup", operation_ids)
        self.assertNotIn("face_slimming", operation_ids)
        self.assertNotIn("skin_texture_smoothing", operation_ids)
        self.assertTrue(analysis["user_intent"]["avoid_face_slimming"])
        self.assertTrue(analysis["user_intent"]["avoid_skin_smoothing"])

    def test_pixel_retouch_filters_explicit_operations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = _portrait(Path(temp_dir) / "input.jpg")
            output_path = Path(temp_dir) / "output.jpg"
            result = render_pixel_retouch(
                input_path,
                output_path,
                scene="portrait",
                aesthetic="natural",
                operations=["skin_cleanup", "skin_texture_smoothing", "face_slimming"],
                strength=0.18,
                user_suggestion="不要瘦脸，不要磨皮",
            )

            self.assertEqual(result["operations_requested"], ["skin_cleanup"])
            self.assertTrue(Path(result["output_path"]).exists())

    def test_external_analysis_prompt_contains_user_suggestion(self):
        request = AnalyzeRequest(
            batch_id="suggestion-test",
            scene="portrait",
            aesthetic="natural",
            edit_level="basic",
            user_suggestion="保持原比例，不要瘦脸",
            photos=[
                AnalyzePhoto(
                    photo_id="p1",
                    file_name="portrait.jpg",
                    preview_path="portrait.jpg",
                )
            ],
        )

        prompt = _analysis_prompt(request, [(request.photos[0], {"width": 100, "height": 120})], "portrait", "natural", "basic")

        self.assertIn('"user_suggestion": "保持原比例，不要瘦脸"', prompt)
        intent = parse_user_intent(request.user_suggestion)
        self.assertTrue(intent["keep_original_ratio"])
        self.assertTrue(intent["avoid_face_slimming"])

    def test_photo_indexed_suggestion_is_split_per_photo(self):
        text = "第一张，突出人物主体，给草地加上蒙版让其更绿，曝光低一点。第二张风景压低建筑物的曝光，突出天空"

        parts = split_user_suggestion_by_photo(text, 2)

        self.assertEqual(len(parts), 2)
        self.assertIn("草地", parts[0])
        self.assertIn("曝光低一点", parts[0])
        self.assertNotIn("建筑物", parts[0])
        self.assertIn("建筑物", parts[1])
        self.assertIn("突出天空", parts[1])
        self.assertNotIn("草地", parts[1])

    def test_photo_specific_intents_are_not_shared_across_batch(self):
        first = "突出人物主体，给草地加上蒙版让其更绿，曝光低一点"
        second = "风景压低建筑物的曝光，突出天空"

        first_intent = parse_user_intent(first)
        second_intent = parse_user_intent(second)

        self.assertTrue(first_intent["subject_focus"])
        self.assertTrue(first_intent["foliage_green_boost"])
        self.assertTrue(first_intent["lower_exposure"])
        self.assertFalse(first_intent["darken_architecture"])
        self.assertTrue(second_intent["darken_architecture"])
        self.assertTrue(second_intent["sky_focus"])
        self.assertFalse(second_intent["foliage_green_boost"])

        first_deltas = parameter_deltas_from_user_suggestion(first, "portrait")
        second_deltas = parameter_deltas_from_user_suggestion(second, "landscape")
        self.assertLess(first_deltas["exposure"], 0)
        self.assertLess(second_deltas["exposure"], 0)
        self.assertIn("dehaze", second_deltas)

    def test_planner_uses_photo_specific_suggestions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            p1 = _portrait(Path(temp_dir) / "p1.jpg")
            p2 = Path(temp_dir) / "p2.jpg"
            Image.new("RGB", (220, 140), (92, 140, 210)).save(p2)
            request = AnalyzeRequest(
                batch_id="photo-specific-suggestion",
                scene="portrait",
                aesthetic="natural",
                edit_level="basic_plus_advanced_execute",
                user_suggestion="第一张，突出人物主体，给草地加上蒙版让其更绿，曝光低一点。第二张风景压低建筑物的曝光，突出天空",
                photos=[
                    AnalyzePhoto(photo_id="p1", file_name="p1.jpg", preview_path=p1),
                    AnalyzePhoto(photo_id="p2", file_name="p2.jpg", preview_path=str(p2)),
                ],
            )

            with patch("app.ai_planner.load_ai_config", return_value=AIConfig(provider="mock", enabled=False)):
                response = Planner().analyze(request)

        first, second = response.photos
        self.assertIn("草地", first.local_analysis["user_suggestion"])
        self.assertNotIn("建筑物", first.local_analysis["user_suggestion"])
        self.assertIn("建筑物", second.local_analysis["user_suggestion"])
        self.assertNotIn("草地", second.local_analysis["user_suggestion"])
        self.assertEqual(first.advanced_plan["lightroom_settings"]["SaturationAdjustmentGreen"], 12)
        first_ops = {item["id"] for item in first.local_analysis["operations"]}
        second_ops = {item["id"] for item in second.local_analysis["operations"]}
        self.assertIn("foliage_green_boost", first_ops)
        self.assertNotIn("foliage_green_boost", second_ops)
        self.assertIn("architecture_darken", second_ops)
        self.assertNotIn("architecture_darken", first_ops)

    def test_subject_vignette_intent_outputs_lightroom_settings(self):
        intent = parse_user_intent("突出人物主体，四周加上暗角")
        self.assertTrue(intent["subject_focus"])
        self.assertTrue(intent["vignette"])

        plan = build_advanced_plan(
            {"avg_saturation": 42, "bright_ratio": 0.08, "dark_ratio": 0.12},
            "portrait",
            "natural",
            "basic_plus_advanced_execute",
            {"enabled": False},
            {"user_intent": intent},
        )

        self.assertTrue(plan["applied"])
        self.assertLess(plan["lightroom_settings"]["PostCropVignetteAmount"], 0)
        self.assertEqual(plan["lightroom_settings"]["PostCropVignetteFeather"], 78)

    def test_negative_vignette_intent_is_respected(self):
        intent = parse_user_intent("突出主体，但是不要暗角")
        plan = build_advanced_plan(
            {"avg_saturation": 42},
            "portrait",
            "natural",
            "basic_plus_advanced_execute",
            {"enabled": False},
            {"user_intent": intent},
        )

        self.assertNotIn("PostCropVignetteAmount", plan["lightroom_settings"])


if __name__ == "__main__":
    unittest.main()
