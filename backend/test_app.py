import base64
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

from app import app


class FlaskAppTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_homepage_is_served_by_flask(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ECHO AI", response.data)
        response.close()

    def test_health_reports_gemini_provider(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["aiProvider"], "Gemini")

    def test_chat_uses_gemini_and_returns_reply(self):
        gemini_client = MagicMock()
        gemini_client.__enter__.return_value = gemini_client
        gemini_client.models.generate_content.return_value = SimpleNamespace(text="Recycle it safely.")

        with patch("app.get_gemini_client", return_value=gemini_client):
            response = self.client.post("/api/chat", json={
                "message": "How do I recycle a battery?",
                "history": [{"role": "user", "text": "Hello"}, {"role": "model", "text": "Hi!"}],
                "lang": "en",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"reply": "Recycle it safely."})
        gemini_client.models.generate_content.assert_called_once()
        self.assertEqual(gemini_client.models.generate_content.call_args.kwargs["model"], "gemini-3.5-flash-lite")
        gemini_client.__exit__.assert_called_once()

    def test_image_analysis_uses_gemini_vision(self):
        image_buffer = io.BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image_buffer, format="JPEG")
        image_data_url = "data:image/jpeg;base64," + base64.b64encode(image_buffer.getvalue()).decode("ascii")
        gemini_result = {
            "matchedKey": "phone",
            "confidence": 0.91,
            "detectedName": "Smartphone",
            "detectedBrand": "Unknown",
            "damageObserved": "No visible damage.",
            "aiDecision": "RECYCLE",
            "reasons": ["Contains a rechargeable battery."],
            "recommendation": "Use an approved e-waste collection point.",
        }
        gemini_client = MagicMock()
        gemini_client.__enter__.return_value = gemini_client
        gemini_client.models.generate_content.return_value = SimpleNamespace(text=json.dumps(gemini_result))

        with patch("app.get_gemini_client", return_value=gemini_client):
            response = self.client.post("/api/analyze-ewaste", json={
                "imageDataUrl": image_data_url,
                "lang": "en",
            })

        self.assertEqual(response.status_code, 200)
        analysis = response.get_json()["analysis"]
        self.assertEqual(analysis["matchedKey"], "phone")
        self.assertEqual(analysis["model"], "gemini-3.5-flash-lite")
        gemini_client.models.generate_content.assert_called_once()
        gemini_client.__exit__.assert_called_once()

    def test_missing_api_key_is_reported_to_chat_client(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            response = self.client.post("/api/chat", json={"message": "Hello"})

        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.get_json()["error"])

    def test_invalid_image_is_rejected(self):
        response = self.client.post("/api/analyze-ewaste", json={"imageDataUrl": "not an image"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())


if __name__ == "__main__":
    unittest.main()
