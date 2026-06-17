import unittest

from app.dashboard import (
    _advanced_batch_status,
    _advanced_plan_html,
    _photo_modifications_html,
    _preview_compare_grid,
    _retouch_batch_status,
    _scene_summary,
    _user_suggestion_html,
)


class DashboardSummaryTests(unittest.TestCase):
    def test_scene_summary_lists_all_detected_scenes(self):
        html_text = _scene_summary(
            {
                "photos": [
                    {"detected_scene": "portrait"},
                    {"detected_scene": "landscape"},
                    {"detected_scene": "landscape"},
                ]
            }
        )

        self.assertIn("风景 2 张", html_text)
        self.assertIn("人像 1 张", html_text)

    def test_user_suggestion_is_rendered_in_edit_summary(self):
        html = _user_suggestion_html("保持原比例，重点压天空高光")

        self.assertIn("用户建议", html)
        self.assertIn("保持原比例", html)
        self.assertIn("重点压天空高光", html)

    def test_photo_modifications_include_advanced_lightroom_settings(self):
        html = _photo_modifications_html(
            {
                "changed_params": [
                    {"label": "曝光", "value": 0.2, "direction": "positive", "text": "提亮曝光 0.2 档"}
                ],
                "advanced_plan": {
                    "applied": True,
                    "lightroom_settings": {
                        "CropLeft": 0.02,
                        "SaturationAdjustmentGreen": -18,
                    },
                },
            }
        )

        self.assertIn("基础参数", html)
        self.assertIn("进阶参数", html)
        self.assertIn("绿色饱和度", html)
        self.assertIn("裁剪左边界", html)

    def test_advanced_plan_html_shows_execution_and_pending_sections(self):
        html = _advanced_plan_html(
            {
                "applied": True,
                "lightroom_settings": {"SaturationAdjustmentGreen": -18},
                "sections": [
                    {"name": "混色器", "applied": True, "settings": {"SaturationAdjustmentGreen": -18}},
                    {"name": "pixel_retouch_plan", "applied": False, "settings": {}, "notes": ["face slim"]},
                ],
                "limitations": ["需要 Photoshop 或像素精修执行局部修复。"],
            },
            [],
        )

        self.assertIn("已执行进阶修改", html)
        self.assertIn("绿色饱和度", html)
        self.assertIn("像素精修计划", html)
        self.assertIn("仅记录/待外部精修", html)

    def test_advanced_batch_status_reports_execution_success(self):
        status = _advanced_batch_status(
            [
                {
                    "advanced_plan": {
                        "applied": True,
                        "lightroom_settings": {"SaturationAdjustmentGreen": -18},
                        "sections": [{"name": "混色器", "applied": True, "settings": {}}],
                    }
                },
                {"advanced_plan": {"applied": False, "sections": [{"name": "蒙版", "applied": False}]}},
            ]
        )

        self.assertEqual(status["code"], "partial")
        self.assertEqual(status["applied_photo_count"], 1)
        self.assertEqual(status["planned_photo_count"], 2)
        self.assertEqual(status["setting_count"], 1)

    def test_retouch_status_reports_pixel_and_photoshop_flows(self):
        pixel = _retouch_batch_status(
            [{"status": "ok", "operations_applied": [{"id": "skin_cleanup"}, {"id": "face_slimming"}]}],
            [],
            {},
        )
        photoshop = _retouch_batch_status(
            [],
            [
                {"status": "completed", "operations_planned": [{"id": "skin_cleanup"}], "mask_assets": [{"id": "skin"}]},
                {"status": "queued", "operations_planned": [{"id": "face_slimming"}], "mask_assets": [{"id": "face"}]},
            ],
            {},
        )

        self.assertEqual(pixel["label"], "本地像素精修")
        self.assertIn("应用 2 项", pixel["detail"])
        self.assertEqual(photoshop["label"], "Photoshop 待执行")
        self.assertIn("完成 1", photoshop["detail"])
        self.assertIn("蒙版 2", photoshop["detail"])

    def test_retouch_status_reports_planned_operations_before_execution(self):
        status = _retouch_batch_status(
            [],
            [],
            {},
            [
                {
                    "local_analysis": {
                        "pixel_retouch": {"available": True},
                        "operations": [{"id": "skin_cleanup"}, {"id": "face_slimming"}],
                    }
                }
            ],
        )

        self.assertEqual(status["label"], "待执行精修")
        self.assertIn("2 项", status["detail"])

    def test_preview_compare_grid_shows_basic_stage_without_retouch(self):
        html = _preview_compare_grid(
            {
                "photos": [
                    {
                        "file_name": "IMG_001.jpg",
                        "detected_scene": "portrait",
                        "before_preview_url": "/dashboard/image?path=before.jpg",
                        "basic_preview_url": "/dashboard/image?path=basic.jpg",
                    }
                ]
            }
        )

        self.assertIn("修图前", html)
        self.assertIn("基础修后", html)
        self.assertNotIn("精修后", html)

    def test_preview_compare_grid_adds_retouch_stage_when_available(self):
        html = _preview_compare_grid(
            {
                "photos": [
                    {
                        "file_name": "IMG_001.jpg",
                        "detected_scene": "portrait",
                        "before_preview_url": "/dashboard/image?path=before.jpg",
                        "basic_preview_url": "/dashboard/image?path=basic.jpg",
                        "retouch_preview_url": "/dashboard/image?path=final.jpg",
                    }
                ]
            }
        )

        self.assertIn("修图前", html)
        self.assertIn("基础修后", html)
        self.assertIn("精修后", html)


if __name__ == "__main__":
    unittest.main()
