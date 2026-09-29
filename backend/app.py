import base64
import binascii
import io
import json
import logging
import math
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from google import genai
from google.genai import types
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge


load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 14 * 1024 * 1024

FRONTEND_FILE = Path(__file__).resolve().parent.parent / "frontend" / "E WASTE ECHO AI APP.html"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_ITEMS = {
    "phone": "smartphone or mobile phone",
    "charger": "electrical charger, power adapter, or charging cable",
    "laptop": "laptop or notebook computer",
    "fan": "household electric standing or table fan",
    "portable_fan": "small portable USB handheld fan",
    "earphone": "earphones, earbuds, or headphones",
    "powerbank": "portable power bank battery",
    "microwave": "microwave oven",
    "blender": "kitchen blender or food mixer",
    "tv": "television or computer monitor",
    "printer": "computer printer",
    "smartwatch": "smartwatch or fitness tracker",
    "rice_cooker": "electric rice cooker",
    "vacuum_cleaner": "vacuum cleaner",
    "keyboard": "computer keyboard",
}


def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured. Add it to backend/.env.")
    return genai.Client(api_key=api_key)


def decode_image_data_url(image_data_url: str) -> tuple[bytes, str]:
    match = re.fullmatch(
        r"data:image/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=\r\n]+)",
        image_data_url,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError("Image must be a base64 JPEG, PNG, or WebP data URL.")

    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Image data is not valid base64.") from exc

    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be between 1 byte and 10 MB.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Uploaded data is not a readable image.") from exc

    mime_types = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    mime_type = mime_types.get(image_format)
    if mime_type is None:
        raise ValueError("Image must be a JPEG, PNG, or WebP.")
    return image_bytes, mime_type


def parse_analysis(response_text: str) -> dict:
    try:
        result = json.loads(response_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Gemini returned an invalid image analysis.") from exc

    if not isinstance(result, dict):
        raise ValueError("Gemini returned an invalid image analysis.")

    matched_key = result.get("matchedKey")
    if matched_key != "unsupported" and matched_key not in SUPPORTED_ITEMS:
        raise ValueError("Gemini returned an unsupported item category.")

    text_fields = ("detectedName", "detectedBrand", "damageObserved", "aiDecision", "recommendation")
    if any(not isinstance(result.get(field), str) or not result[field].strip() for field in text_fields):
        raise ValueError("Gemini returned incomplete image analysis.")

    confidence = result.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("Gemini returned an invalid confidence score.")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("Gemini returned an invalid confidence score.")

    reasons = result.get("reasons")
    if not isinstance(reasons, list) or not reasons or any(not isinstance(reason, str) for reason in reasons):
        raise ValueError("Gemini returned invalid recycling reasons.")

    return {
        "matchedKey": matched_key,
        "confidence": round(float(confidence), 4),
        "detectedName": result["detectedName"].strip(),
        "detectedBrand": result["detectedBrand"].strip(),
        "damageObserved": result["damageObserved"].strip(),
        "aiDecision": result["aiDecision"].strip(),
        "reasons": reasons,
        "recommendation": result["recommendation"].strip(),
        "model": GEMINI_MODEL,
    }


@app.get("/")
def index():
    return send_file(FRONTEND_FILE)


@app.get("/health")
def healthcheck():
    return jsonify({"status": "ok", "service": "ECHO AI Backend", "aiProvider": "Gemini"})


@app.post("/api/analyze-ewaste")
def analyze_ewaste():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be valid JSON."}), 400

    image_data_url = payload.get("imageDataUrl")
    if not isinstance(image_data_url, str):
        return jsonify({"error": "imageDataUrl is required."}), 400

    try:
        image_bytes, mime_type = decode_image_data_url(image_data_url)
    except ValueError as exc:
        status = 413 if "10 MB" in str(exc) else 400
        return jsonify({"error": str(exc)}), status

    language = "English" if payload.get("lang") == "en" else "Bahasa Melayu"
    item_list = "\n".join(f'- "{key}": {description}' for key, description in SUPPORTED_ITEMS.items())
    prompt = f"""Analyze this image for the ECHO AI e-waste recycling app.
Respond only with a JSON object containing these exact keys:
matchedKey, confidence, detectedName, detectedBrand, damageObserved, aiDecision, reasons, recommendation.
Use one supported matchedKey from the list below, or "unsupported" if the image is not clearly one of these items:
{item_list}
Write every text value and reason in {language}. confidence must be a number from 0 to 1 representing your estimate, not a calibrated probability.
If damage cannot be confirmed from the image, say so instead of claiming damage. Do not guess a brand.
For unsupported images use matchedKey "unsupported", detectedName "Not supported", aiDecision "NOT SUPPORTED", and explain that the image does not clearly show a supported e-waste item.
Give concise, safe disposal guidance. Do not claim a specific drop-off location unless it is certain."""

    try:
        with get_gemini_client() as client:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
        analysis = parse_analysis(response.text)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        app.logger.exception("Gemini e-waste image analysis failed")
        return jsonify({"error": f"Gemini image analysis failed: {exc}"}), 502

    return jsonify({
        "success": True,
        "analysis": analysis,
        "lang": payload.get("lang", "bm"),
    })


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be valid JSON."}), 400

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message is required."}), 400
    if len(message) > 4000:
        return jsonify({"error": "message must be 4,000 characters or fewer."}), 400

    history = payload.get("history", [])
    if not isinstance(history, list):
        return jsonify({"error": "history must be a list."}), 400
    contents = []
    for entry in history[-20:]:
        if not isinstance(entry, dict) or entry.get("role") not in ("user", "model"):
            return jsonify({"error": "Each history entry must have a user or model role."}), 400
        text = entry.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            return jsonify({"error": "Each history entry must contain text up to 4,000 characters."}), 400
        contents.append(types.Content(
            role=entry["role"],
            parts=[types.Part.from_text(text=text)],
        ))

    language = "English" if payload.get("lang") == "en" else "Bahasa Melayu"
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=message.strip())],
    ))

    try:
        with get_gemini_client() as client:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You are ECHOBot, the friendly AI assistant in the ECHO e-waste recycling app. "
                        f"Reply in {language}. Help with e-waste identification, safe recycling, repair-versus-recycle "
                        "decisions, and app usage. Give safety-first advice, especially for lithium batteries and "
                        "electrical repairs. Do not invent collection locations, current programs, or voucher details; "
                        "be clear when information needs verification."
                    ),
                ),
            )
        reply = response.text
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Gemini returned an empty chat response.")
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        app.logger.exception("Gemini chat request failed")
        return jsonify({"error": f"Gemini chat failed: {exc}"}), 502

    return jsonify({"reply": reply.strip()})


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify({"error": "Request is too large. Images must be 10 MB or smaller."}), 413


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="127.0.0.1", port=8000)
