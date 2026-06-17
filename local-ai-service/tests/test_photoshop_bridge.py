import os
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.photoshop_bridge import (
    build_photoshop_jsx,
    create_photoshop_job,
    get_next_photoshop_job,
    mark_photoshop_job_complete,
    photoshop_status,
)
from app.schemas import PhotoshopJobRequest


class PhotoshopBridgeTests(unittest.TestCase):
    def setUp(self):
        self._old_run_root = os.environ.get("AI_RETOUCH_RUN_ROOT")
        self._old_action_config = os.environ.get("AI_RETOUCH_PHOTOSHOP_ACTIONS")
        self._temp_dir = tempfile.TemporaryDirectory()
        os.environ["AI_RETOUCH_RUN_ROOT"] = self._temp_dir.name

    def tearDown(self):
        if self._old_run_root is None:
            os.environ.pop("AI_RETOUCH_RUN_ROOT", None)
        else:
            os.environ["AI_RETOUCH_RUN_ROOT"] = self._old_run_root
        if self._old_action_config is None:
            os.environ.pop("AI_RETOUCH_PHOTOSHOP_ACTIONS", None)
        else:
            os.environ["AI_RETOUCH_PHOTOSHOP_ACTIONS"] = self._old_action_config
        self._temp_dir.cleanup()

    def test_create_job_writes_manifest_and_script(self):
        input_path = Path(self._temp_dir.name) / "input.jpg"
        Image.new("RGB", (64, 48), (120, 100, 90)).save(input_path)
        mask_path = Path(self._temp_dir.name) / "skin-mask.png"
        Image.new("L", (64, 48), 255).save(mask_path)

        job = create_photoshop_job(
            PhotoshopJobRequest(
                batch_id="ps-test",
                photo_id="photo-1",
                input_path=str(input_path),
                quality_mode="commercial",
                operations=[
                    {"type": "skin_smoothing"},
                    {"type": "frequency_separation", "region_id": "skin", "mask_path": str(mask_path)},
                    {"type": "face_liquify", "region_id": "face"},
                    {"type": "face_relight"},
                    {"type": "architecture_darken", "region_id": "foreground"},
                    {"type": "foliage_green_boost", "region_id": "foliage"},
                ],
                mask_assets=[{"id": "skin", "path": str(mask_path), "bbox": {"left": 0, "top": 0, "right": 1, "bottom": 1}}],
                user_suggestion="不要过度磨皮",
            )
        )

        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["quality_mode"], "commercial")
        self.assertEqual(len(job["mask_assets"]), 1)
        self.assertTrue(Path(job["job_path"]).exists())
        self.assertTrue(Path(job["script_path"]).exists())
        self.assertEqual(get_next_photoshop_job("ps-test")["job_id"], "photo-1")

        script = Path(job["script_path"]).read_text(encoding="utf-8")
        self.assertIn("AI skin smoothing candidate", script)
        self.assertIn("AI frequency separation low-frequency candidate", script)
        self.assertIn("AI face liquify candidate", script)
        self.assertIn("AI local light candidate", script)
        self.assertIn("AI architecture exposure candidate", script)
        self.assertIn("AI foliage green boost candidate", script)
        self.assertIn("addMaskGuide", script)
        self.assertIn("skin-mask.png", script)
        self.assertIn('"quality_mode":"commercial"', script)
        self.assertIn("不要过度磨皮", script)

    def test_mark_complete_updates_job(self):
        input_path = Path(self._temp_dir.name) / "input.jpg"
        Image.new("RGB", (64, 48), (120, 100, 90)).save(input_path)
        job = create_photoshop_job(PhotoshopJobRequest(batch_id="ps-test", photo_id="photo-2", input_path=str(input_path)))

        updated = mark_photoshop_job_complete(job["job_id"], job["batch_id"], {"message": "done"})

        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["message"], "done")
        self.assertIsNone(get_next_photoshop_job("ps-test"))

    def test_action_config_is_embedded_in_generated_jsx(self):
        input_path = Path(self._temp_dir.name) / "input.jpg"
        Image.new("RGB", (64, 48), (120, 100, 90)).save(input_path)
        config_path = Path(self._temp_dir.name) / "photoshop_actions.json"
        config_path.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "actions": {
                        "skin_smoothing": {
                            "set": "AI Retouch",
                            "action": "Skin Smoothing",
                            "required": False,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        os.environ["AI_RETOUCH_PHOTOSHOP_ACTIONS"] = str(config_path)

        job = create_photoshop_job(
            PhotoshopJobRequest(
                batch_id="ps-test",
                photo_id="photo-action",
                input_path=str(input_path),
                operations=[{"type": "skin_smoothing"}],
            )
        )

        self.assertEqual(job["operations"][0]["photoshop_action"]["set"], "AI Retouch")
        script = Path(job["script_path"]).read_text(encoding="utf-8")
        self.assertIn("runActionHook", script)
        self.assertIn("app.doAction", script)
        self.assertIn("AI Retouch", script)
        self.assertIn("Skin Smoothing", script)
        self.assertIn("action_log", script)

    def test_build_jsx_escapes_windows_paths(self):
        job = {
            "job_id": "p",
            "input_path": r"C:\in\a.jpg",
            "output_path": r"C:\out\a.jpg",
            "psd_path": r"C:\out\a.psd",
            "marker_path": r"C:\out\a.result.json",
            "operations": [],
            "user_suggestion": "",
        }

        jsx = build_photoshop_jsx(job)

        self.assertIn("C:/in/a.jpg", jsx)
        self.assertIn("C:/out/a.jpg", jsx)

    def test_photoshop_status_reports_configured_path(self):
        status = photoshop_status()

        self.assertIn("photoshop_exe", status)
        self.assertEqual(status["mode"], "jsx_desktop_bridge")


if __name__ == "__main__":
    unittest.main()
