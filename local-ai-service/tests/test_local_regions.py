import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.image_metrics import image_metrics
from app.local_regions import analyze_local_regions
from app.pixel_retouch import render_pixel_retouch


def _portrait(path: Path) -> str:
    image = Image.new("RGB", (180, 220), (76, 78, 82))
    draw = ImageDraw.Draw(image)
    draw.ellipse((54, 42, 126, 132), fill=(196, 132, 96))
    draw.rectangle((74, 126, 108, 190), fill=(184, 118, 88))
    draw.ellipse((82, 80, 88, 86), fill=(95, 56, 50))
    image.save(path)
    return str(path)


def _landscape(path: Path) -> str:
    image = Image.new("RGB", (220, 140), (90, 130, 90))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 220, 72), fill=(90, 150, 216))
    draw.rectangle((0, 72, 220, 140), fill=(74, 126, 58))
    draw.polygon([(120, 44), (190, 140), (50, 140)], fill=(96, 110, 72))
    image.save(path)
    return str(path)


class LocalRegionTests(unittest.TestCase):
    def test_portrait_analysis_recommends_face_pixel_operations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = _portrait(Path(temp_dir) / "portrait.jpg")
            metrics = image_metrics(path)
            analysis = analyze_local_regions(path, metrics, "portrait", "natural")

        region_ids = {item["id"] for item in analysis["regions"]}
        operation_ids = {item["id"] for item in analysis["operations"]}
        self.assertIn("face", region_ids)
        self.assertIn("skin_cleanup", operation_ids)
        self.assertIn("face_slimming", operation_ids)

    def test_landscape_analysis_recommends_sky_and_light_operations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = _landscape(Path(temp_dir) / "landscape.jpg")
            metrics = image_metrics(path)
            analysis = analyze_local_regions(path, metrics, "blue_sky", "natural")

        region_ids = {item["id"] for item in analysis["regions"]}
        operation_ids = {item["id"] for item in analysis["operations"]}
        self.assertIn("sky", region_ids)
        self.assertIn("sky_light_balance", operation_ids)
        self.assertIn("landscape_dodge_burn", operation_ids)

    def test_pixel_retouch_writes_output(self):
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
            )

            self.assertEqual(result["status"], "ok")
            self.assertTrue(Path(result["output_path"]).exists())
            self.assertGreaterEqual(len(result["operations_applied"]), 1)


if __name__ == "__main__":
    unittest.main()
