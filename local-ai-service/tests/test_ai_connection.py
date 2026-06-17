import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from app.ai_connection import call_ai_text, test_ai_config
from app.config import AIConfig


class FakeHTTPResponse:
    status = 200

    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.payload


class AIConnectionTests(unittest.TestCase):
    def test_responses_api_detection_posts_to_responses_endpoint(self):
        config = AIConfig(
            provider="openai_compatible",
            api_key="sk-test-secret-value",
            base_url="https://api.example.com/v1",
            model="gpt-test",
            wire_api="responses",
            enabled=True,
        )

        def fake_urlopen(request, timeout):
            self.assertEqual(request.full_url, "https://api.example.com/v1/responses")
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["model"], "gpt-test")
            self.assertEqual(request.headers["Authorization"], "Bearer sk-test-secret-value")
            return FakeHTTPResponse({"output_text": "OK"})

        with patch("app.ai_connection.urllib.request.urlopen", fake_urlopen):
            result = test_ai_config(config, timeout=1)

        self.assertTrue(result["passed"])
        self.assertEqual(result["sample"], "OK")

    def test_ctoken_root_base_url_is_normalized_to_v1(self):
        config = AIConfig(
            provider="custom",
            api_key="sk-test-secret-value",
            base_url="https://ctoken.top/",
            model="gpt-test",
            wire_api="responses",
            enabled=True,
        )

        def fake_urlopen(request, timeout):
            self.assertEqual(request.full_url, "https://ctoken.top/v1/responses")
            return FakeHTTPResponse({"output_text": "OK"})

        with patch("app.ai_connection.urllib.request.urlopen", fake_urlopen):
            result = test_ai_config(config, timeout=1)

        self.assertTrue(result["passed"])

    def test_responses_api_can_send_image_inputs(self):
        config = AIConfig(
            provider="openai_compatible",
            api_key="sk-test-secret-value",
            base_url="https://api.example.com/v1",
            model="gpt-test",
            wire_api="responses",
            enabled=True,
        )

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            content = payload["input"][0]["content"]
            self.assertEqual(content[0]["type"], "input_text")
            self.assertEqual(content[1]["type"], "input_image")
            self.assertEqual(content[1]["image_url"], "data:image/jpeg;base64,abc")
            return FakeHTTPResponse({"output_text": "OK"})

        with patch("app.ai_connection.urllib.request.urlopen", fake_urlopen):
            result = call_ai_text(config, "look", image_urls=["data:image/jpeg;base64,abc"], timeout=1)

        self.assertTrue(result["passed"])
        self.assertEqual(result["sample"], "OK")

    def test_http_error_is_sanitized(self):
        config = AIConfig(
            provider="openai_compatible",
            api_key="sk-test-secret-value",
            base_url="https://api.example.com/v1",
            model="gpt-test",
            wire_api="responses",
            enabled=True,
        )

        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"error":"bad key sk-test-secret-value"}'),
            )

        with patch("app.ai_connection.urllib.request.urlopen", fake_urlopen):
            result = test_ai_config(config, timeout=1)

        self.assertFalse(result["passed"])
        self.assertNotIn("sk-test-secret-value", result["message"])
        self.assertIn("***", result["message"])

    def test_legacy_completions_detection_matches_engine_endpoint(self):
        config = AIConfig(
            provider="custom",
            api_key="sk-test-secret-value",
            base_url="https://api.example.com/v1",
            model="davinci-codex",
            wire_api="legacy_completions",
            enabled=True,
        )

        def fake_urlopen(request, timeout):
            self.assertEqual(request.full_url, "https://api.example.com/v1/engines/davinci-codex/completions")
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["prompt"], "请只回复 OK。")
            self.assertNotIn("model", payload)
            return FakeHTTPResponse({"choices": [{"text": "OK"}]})

        with patch("app.ai_connection.urllib.request.urlopen", fake_urlopen):
            result = test_ai_config(config, timeout=1)

        self.assertTrue(result["passed"])
        self.assertEqual(result["sample"], "OK")

    def test_completions_detection_posts_model_to_completions_endpoint(self):
        config = AIConfig(
            provider="custom",
            api_key="sk-test-secret-value",
            base_url="https://api.example.com/v1",
            model="text-davinci-003",
            wire_api="completions",
            enabled=True,
        )

        def fake_urlopen(request, timeout):
            self.assertEqual(request.full_url, "https://api.example.com/v1/completions")
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["model"], "text-davinci-003")
            self.assertEqual(payload["prompt"], "请只回复 OK。")
            return FakeHTTPResponse({"choices": [{"text": "OK"}]})

        with patch("app.ai_connection.urllib.request.urlopen", fake_urlopen):
            result = test_ai_config(config, timeout=1)

        self.assertTrue(result["passed"])
        self.assertEqual(result["sample"], "OK")

    def test_openai_relay_auto_detects_working_completions_endpoint(self):
        config = AIConfig(
            provider="openai_relay",
            api_key="sk-test-secret-value",
            base_url="https://relay.example.com/v1",
            model="text-davinci-003",
            wire_api="openai_relay",
            enabled=True,
        )
        visited = []

        def fake_urlopen(request, timeout):
            visited.append(request.full_url)
            if request.full_url.endswith("/chat/completions"):
                raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b"not found"))
            return FakeHTTPResponse({"choices": [{"text": "OK"}]})

        with patch("app.ai_connection.urllib.request.urlopen", fake_urlopen):
            result = test_ai_config(config, timeout=1)

        self.assertTrue(result["passed"])
        self.assertEqual(result["wire_api"], "completions")
        self.assertEqual(
            visited,
            [
                "https://relay.example.com/v1/chat/completions",
                "https://relay.example.com/v1/completions",
            ],
        )
        self.assertEqual(len(result["attempts"]), 2)

    def test_swapped_key_and_url_are_reported(self):
        config = AIConfig(
            provider="custom",
            api_key="https://api.example.com/v1",
            base_url="sk-test-secret-value",
            model="gpt-test",
            wire_api="responses",
            enabled=True,
        )

        result = test_ai_config(config, timeout=1)

        self.assertFalse(result["passed"])
        self.assertTrue(any("填反" in item for item in result["warnings"]))

    def test_cloudflare_1010_error_gets_actionable_message(self):
        config = AIConfig(
            provider="custom",
            api_key="sk-test-secret-value",
            base_url="https://ctoken.top",
            model="gpt-test",
            wire_api="responses",
            enabled=True,
        )
        payload = {
            "cloudflare_error": True,
            "error_code": 1010,
            "error_name": "browser_signature_banned",
            "detail": "The site owner has blocked access based on your browser's signature.",
            "ray_id": "test-ray",
        }

        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                403,
                "Forbidden",
                {},
                io.BytesIO(json.dumps(payload).encode("utf-8")),
            )

        with patch("app.ai_connection.urllib.request.urlopen", fake_urlopen):
            result = test_ai_config(config, timeout=1)

        self.assertFalse(result["passed"])
        self.assertIn("Cloudflare", result["message"])
        self.assertIn("http://ctoken.top/v1/", result["message"])
        self.assertTrue(any("/v1" in item for item in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
