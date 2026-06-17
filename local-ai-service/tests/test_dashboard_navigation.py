import unittest
from html.parser import HTMLParser

from app.dashboard import _preview_image_html, _runs_table, _safe_dashboard_return_url


class _HrefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        values = dict(attrs)
        if "href" in values:
            self.hrefs.append(values["href"])


class DashboardNavigationTests(unittest.TestCase):
    def test_batch_links_url_encode_path_segments(self):
        html = _runs_table(
            [
                {
                    "batch_id": "batch 1&2",
                    "updated_at": "2026-06-17T12:00:00+08:00",
                    "file_count": 1,
                    "photo_count": 1,
                    "files": ["analyze.json"],
                }
            ]
        )
        parser = _HrefParser()
        parser.feed(html)

        self.assertIn("/dashboard/runs/batch%201%262", parser.hrefs)
        self.assertIn("/dashboard/runs/batch%201%262/edit-summary", parser.hrefs)
        self.assertNotIn("/dashboard/runs/batch 1&2", parser.hrefs)

    def test_preview_view_link_is_built_before_html_escape(self):
        html = _preview_image_html("/dashboard/image?path=C%3A%2Ftmp%2Fa%26b.jpg", "before")
        parser = _HrefParser()
        parser.feed(html)

        self.assertEqual(parser.hrefs, ["/dashboard/image-view?path=C%3A%2Ftmp%2Fa%26b.jpg"])

    def test_preview_view_link_includes_return_url(self):
        html = _preview_image_html(
            "/dashboard/image?path=C%3A%2Ftmp%2Fa%26b.jpg",
            "before",
            "/dashboard/runs/batch 1&2/edit-summary",
        )
        parser = _HrefParser()
        parser.feed(html)

        self.assertEqual(
            parser.hrefs,
            [
                "/dashboard/image-view?path=C%3A%2Ftmp%2Fa%26b.jpg"
                "&return_to=%2Fdashboard%2Fruns%2Fbatch%201%262%2Fedit-summary"
            ],
        )

    def test_image_view_return_url_stays_internal(self):
        self.assertEqual(_safe_dashboard_return_url("/dashboard/runs/batch-1"), "/dashboard/runs/batch-1")
        self.assertEqual(_safe_dashboard_return_url("https://example.com/dashboard"), "/dashboard/runs")
        self.assertEqual(_safe_dashboard_return_url("//example.com/dashboard"), "/dashboard/runs")


if __name__ == "__main__":
    unittest.main()
