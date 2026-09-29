# ECHO AI Flask App

The Flask app serves the ECHO AI frontend and provides Gemini-powered e-waste image analysis and chat. Images are checked and sent to Gemini; the browser never receives the API key.

## Setup

1. Install Python 3.10–3.13.
2. Create a Gemini API key in Google AI Studio.
3. Create `backend/.env` with:

   ```text
   GEMINI_API_KEY=your_api_key
   ```

   Optionally set `GEMINI_MODEL` to choose another Gemini model. The default is `gemini-3.5-flash-lite`; `gemini-2.5-flash-lite` is unavailable to new users with this API key.
4. Double-click `backend/start-backend.bat`. On first launch it creates a virtual environment and installs dependencies.
5. Open <http://localhost:8000> and leave the backend window running.
6. Press Ctrl+C in the backend window to stop the app.

Alternatively, from the `backend` directory:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

The frontend is served by Flask at `/`; do not open its HTML file directly. The backend needs internet access and a valid Gemini API key for AI endpoints.

## API

### `POST /api/analyze-ewaste`

Request:

```json
{
  "imageDataUrl": "data:image/jpeg;base64,...",
  "filename": "phone.jpg",
  "lang": "bm"
}
```

Accepts JPEG, PNG, and WebP images up to 10 MB. Returns `success`, `lang`, and an `analysis` object with `matchedKey`, `confidence`, `detectedName`, `detectedBrand`, `damageObserved`, `aiDecision`, `reasons`, `recommendation`, and `model`. The confidence is Gemini's estimate, not a calibrated probability. Image analysis may not establish damage reliably; treat disposal and repair advice as guidance and verify safety-critical decisions.

### `POST /api/chat`

Request:

```json
{
  "message": "How do I safely recycle a swollen battery?",
  "history": [],
  "lang": "en"
}
```

Returns `{"reply": "..."}`. Chat history is limited to the most recent 20 user/model messages.

### `GET /health`

Returns service status and the configured AI provider. This check does not make a Gemini API request.

## Sharing and deployment

Do not share or commit `.env`, API keys, `.venv/`, or generated model files.

### Deploy to Render

1. Push the project to a GitHub repository. Include `render.yaml`, `backend/`, and `frontend/`; do not upload `.env`, `.venv/`, or API keys.
2. In Render, select **New → Blueprint** and connect the GitHub repository. Render reads the root `render.yaml` and creates the Flask web service.
3. In the service's environment settings, add `GEMINI_API_KEY` with your Gemini API key. The key is a secret and should only be entered in Render's dashboard, not in `render.yaml` or source control.
4. Wait for the build and deploy to finish, then open the `onrender.com` URL shown for the service. Render uses `/health` to check the app.

The Blueprint installs dependencies from `backend/requirements.txt` and runs Flask with Gunicorn, bound to Render's assigned port. Flask serves the frontend from the sibling `frontend/` folder. The selected model is `gemini-3.5-flash-lite`. Free Render services may sleep when idle, so the first request after inactivity can take longer.

The Gemini API key was previously shared in chat. For deployment, rotate it in Google AI Studio and enter the new key in Render's environment settings. Do not reuse a key that may have been exposed.
