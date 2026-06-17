import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.photoshop_retouch import prepare_photoshop_retouch
from app.schemas import PhotoshopRetouchRequest


def _portrait(path: Path) -> str:
    image = Image.new("RGB", (180, 220), (76, 78, 82))
    draw = ImageDraw.Draw(image)
    draw.ellipse((54, 42, 126, 132), fill=(196, 132, 96))
    draw.rectangle((74, 126, 108, 190), fill=(184, 118, 88))
    image.save(path)
    return str(path)


class PhotoshopRetouchTests(unittest.TestCase):
    def setUp(self):
        self._old_run_root = os.environ.get("AI_RETOUCH_RUN_ROOT")
        self._temp_dir = tempfile.TemporaryDirectory()
        os.environ["AI_RETOUCH_RUN_ROOT"] = self._temp_dir.name

    def tearDown(self):
        if self._old_run_root is None:
            os.environ.pop("AI_RETOUCH_RUN_ROOT", None)
        else:
            os.environ["AI_RETOUCH_RUN_ROOT"] = self._old_run_root
        self._temp_dir.cleanup()

    def test_prepare_photoshop_retouch_builds_ai_job(self):
        input_path = _portrait(Path(self._temp_dir.name) / "portrait.jpg")

        result = prepare_photoshop_retouch(
            PhotoshopRetouchRequest(
                batch_id="ps-retouch-test",
                photo_id="p1",
                input_path=input_path,
                scene="portrait",
                aesthetic="natural",
                operations=["skin_cleanup", "skin_texture_smoothing", "face_slimming"],
                user_suggestion="不要磨皮，只去瑕疵",
            )
        )

        self.assertEqual(result["status"], "queued")
        self.assertIn("skin_cleanup", result["operations_requested"])
        self.assertNotIn("skin_texture_smoothing", result["operations_requested"])
        self.assertNotIn("commercial_skin_retouch", result["operations_requested"])
        self.assertTrue(any(item["type"] == "blemish_cleanup" for item in result["operations_planned"]))
        self.assertTrue(result["mask_assets"])
        self.assertTrue(any(Path(str(item.get("path") or "")).exists() for item in result["mask_assets"]))
        self.assertTrue(Path(result["job"]["job_path"]).exists())
        self.assertTrue(Path(result["job"]["script_path"]).exists())

        script = Path(result["job"]["script_path"]).read_text(encoding="utf-8")
        self.assertIn("AI blemish cleanup candidate", script)
        self.assertIn("AI operations", script)

    def test_prepare_photoshop_retouch_can_queue_without_explicit_operations(self):
        input_path = _portrait(Path(self._temp_dir.name) / "portrait.jpg")

        result = prepare_photoshop_retouch(
            PhotoshopRetouchRequest(
                batch_id="ps-retouch-test",
                photo_id="p2",
                input_path=input_path,
                scene="portrait",
                aesthetic="natural",
            )
        )

        self.assertGreaterEqual(len(result["operations_requested"]), 1)
        self.assertEqual(len(result["operations_requested"]), len(result["operations_planned"]))
        self.assertIn("commercial_skin_retouch", result["operations_requested"])
        self.assertTrue(any(item["type"] == "frequency_separation" for item in result["operations_planned"]))
        self.assertTrue(any(item.get("mask_path") for item in result["operations_planned"]))
        self.assertEqual(result["job"]["quality_mode"], "commercial")

        script = Path(result["job"]["script_path"]).read_text(encoding="utf-8")
        self.assertIn("AI frequency separation low-frequency candidate", script)
        self.assertIn("AI mask guide", script)


if __name__ == "__main__":
    unittest.main()
