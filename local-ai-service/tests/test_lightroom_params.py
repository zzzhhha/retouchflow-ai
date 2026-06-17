import unittest

from app.advanced_edits import build_advanced_plan
from app.ai_planner import crop_suggestion, guarded_scene_override, infer_photo_scene
from app.lightroom_params import (
    apply_deltas,
    clamp_deltas,
    clamp_params,
    make_group_base,
    make_photo_params,
    metric_adjustments,
    resolve_scene_aesthetic,
    style_base,
    supported_aesthetics,
    supported_edit_levels,
    supported_scenes,
    to_lightroom_settings,
)


class LightroomParamsTests(unittest.TestCase):
    def test_clamps_absolute_parameters(self):
        params = clamp_params({"exposure": 4, "highlights": -500, "temperature": 2000})

        self.assertEqual(params["exposure"], 0.8)
        self.assertEqual(params["highlights"], -80)
        self.assertEqual(params["temperature"], 900)

    def test_metric_adjustments_are_partial(self):
        adjustments = metric_adjustments({"avg_luma": 80, "dark_ratio": 0.3})

        self.assertIn("exposure", adjustments)
        self.assertNotIn("sharpening", adjustments)

    def test_group_and_photo_params_do_not_double_defaults(self):
        group = make_group_base(
            "wedding_clean",
            [{"avg_luma": 130, "bright_ratio": 0.02, "dark_ratio": 0.01, "warmth": 10}],
        )
        plan = make_photo_params(group, {"avg_luma": 120, "bright_ratio": 0.04, "dark_ratio": 0.08, "warmth": 5})

        self.assertLessEqual(plan.params["sharpening"], 80)
        self.assertLessEqual(plan.params["noise_reduction"], 55)

    def test_maps_to_lightroom_develop_settings(self):
        settings = to_lightroom_settings({"exposure": 0.25, "contrast": 8, "noise_reduction": 20})

        self.assertEqual(settings["Exposure2012"], 0.25)
        self.assertEqual(settings["Contrast2012"], 8)
        self.assertEqual(settings["LuminanceSmoothing"], 20)
        self.assertEqual(settings["ColorNoiseReduction"], 12)

    def test_review_deltas_are_bounded(self):
        deltas = clamp_deltas({"exposure": 1.0, "temperature": 1000, "highlights": -50})

        self.assertEqual(deltas["exposure"], 0.15)
        self.assertEqual(deltas["temperature"], 250)
        self.assertEqual(deltas["highlights"], -12)

    def test_apply_deltas_keeps_full_parameter_set(self):
        base = style_base("natural_portrait")
        plan = apply_deltas(base, {"exposure": 0.2, "temperature": -1000})

        self.assertIn("Exposure2012", plan.lightroom_settings)
        self.assertEqual(plan.params["temperature"], -250)

    def test_scene_and_aesthetic_supports_nature_workflows(self):
        self.assertIn("landscape", supported_scenes())
        self.assertIn("flower", supported_scenes())
        self.assertIn("grass_tree", supported_scenes())
        self.assertIn("sweet", supported_aesthetics())
        self.assertIn("texture", supported_aesthetics())
        self.assertIn("master", supported_aesthetics())
        self.assertIn("basic_plus_advanced_suggestions", supported_edit_levels())

    def test_legacy_style_maps_to_scene_and_aesthetic(self):
        scene, aesthetic = resolve_scene_aesthetic("wedding_clean", "auto", "auto")

        self.assertEqual(scene, "wedding")
        self.assertEqual(aesthetic, "commercial_clean")

    def test_advanced_execute_outputs_applyable_lightroom_settings(self):
        crop = {"enabled": True, "crop": {"left": 0.02, "top": 0.06, "right": 0.98, "bottom": 0.94}}
        plan = build_advanced_plan(
            {"avg_saturation": 76, "bright_ratio": 0.2, "dark_ratio": 0.1},
            "grass_tree",
            "texture",
            "basic_plus_advanced_execute",
            crop,
        )

        self.assertTrue(plan["applied"])
        self.assertIn("SaturationAdjustmentGreen", plan["lightroom_settings"])
        self.assertIn("CropLeft", plan["lightroom_settings"])

    def test_advanced_suggestion_level_does_not_apply_settings(self):
        plan = build_advanced_plan(
            {"avg_saturation": 50, "bright_ratio": 0.2, "dark_ratio": 0.3},
            "portrait",
            "sweet",
            "basic_plus_advanced_suggestions",
            {"enabled": False},
        )

        self.assertFalse(plan["applied"])
        self.assertEqual(plan["lightroom_settings"], {})
        self.assertGreater(len(plan["sections"]), 0)

    def test_mixed_batch_can_override_portrait_scene_for_landscape_photo(self):
        scene = infer_photo_scene(
            {
                "width": 1600,
                "height": 1000,
                "green_ratio": 0.36,
                "blue_ratio": 0.08,
                "skin_tone_ratio": 0.01,
                "avg_saturation": 42,
                "avg_luma": 125,
                "dark_ratio": 0.08,
                "bright_ratio": 0.1,
            },
            "portrait",
            "auto",
        )

        self.assertEqual(scene, "grass_tree")

    def test_dry_reeds_are_not_classified_as_portrait(self):
        metrics = {
            "width": 586,
            "height": 640,
            "green_ratio": 0.0114,
            "blue_ratio": 0.0368,
            "skin_tone_ratio": 0.4951,
            "warm_orange_ratio": 0.4245,
            "dry_vegetation_ratio": 0.52,
            "avg_saturation": 24.42,
            "avg_luma": 129.49,
            "dark_ratio": 0.0201,
            "bright_ratio": 0.2172,
            "sharpness": 22.12,
            "luma_stddev": 55.46,
        }

        self.assertEqual(infer_photo_scene(metrics, "auto", "auto"), "grass_tree")
        self.assertEqual(guarded_scene_override(metrics, "portrait", "grass_tree"), "grass_tree")

    def test_portrait_crop_is_not_forced_without_person_signal(self):
        suggestion = crop_suggestion(
            {
                "width": 1600,
                "height": 1000,
                "skin_tone_ratio": 0.01,
                "green_ratio": 0.2,
                "blue_ratio": 0.1,
            },
            "portrait",
            "natural",
        )

        self.assertFalse(suggestion["enabled"])
        self.assertIn("避免", suggestion["reason"])

    def test_crop_reasons_vary_by_detected_scene(self):
        grass = crop_suggestion(
            {
                "width": 1600,
                "height": 1200,
                "green_ratio": 0.42,
                "blue_ratio": 0.02,
                "dark_ratio": 0.3,
            },
            "grass_tree",
            "natural",
        )
        sky = crop_suggestion(
            {
                "width": 1600,
                "height": 1200,
                "green_ratio": 0.02,
                "blue_ratio": 0.34,
                "bright_ratio": 0.2,
            },
            "blue_sky",
            "natural",
        )

        self.assertNotEqual(grass["reason"], sky["reason"])
        self.assertNotEqual(grass["crop"], {"left": 0.02, "top": 0.06, "right": 0.98, "bottom": 0.94})


if __name__ == "__main__":
    unittest.main()
