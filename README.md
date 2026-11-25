# Alderbrook Clinic — Voice Appointment Desk

Real-time voice appointment desk featuring Claire, a clinic receptionist built with Pipecat, ElevenLabs STT/TTS, Google Gemini, Silero VAD, FastAPI, and SQLite.

## Stack & Models

- **Voice Pipeline (`backend/pipeline.py`)**: `FastAPIWebsocketTransport` (`BrowserAudioSerializer`) -> `ElevenLabsRealtimeSTTService` (`scribe_v2_realtime`) -> `GoogleLLMService` (`gemini-3.5-flash` with function calling) -> `ElevenLabsTTSService` (`eleven_turbo_v2_5`) -> browser PCM16 audio output, with `SileroVADAnalyzer` for turn detection.
- **LLM Used**: **Google Gemini (`gemini-3.5-flash`)** (configurable via `GEMINI_MODEL` in `.env`).
- **Tools (`backend/tools.py`)**:
  - `check_doctor_availability`: Looks up open slots in SQLite by doctor, specialty, or date.
  - `book_appointment`: Books an open slot using the caller's verbally confirmed phone number.
  - `cancel_appointment`: Cancels an existing appointment matched by the caller's phone number and frees the slot.
- **Storage (`backend/database.py`)**: SQLite (`clinic.db`), seeded on first run with four doctors and three days of slots.
- **Dashboard (`frontend/`)**: Displays doctor schedules, open/booked slot filters, and appointments updated live over Server-Sent Events (`/api/events`), plus a **Try Call** phone modal with reactive waveform, mute/end controls, live transcript, and confirmation cards.

## Running Locally

1. Create and activate a virtual environment:

   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:

   ```bash
   cp .env.example .env
   ```

   Open `.env` and fill in `ELEVENLABS_API_KEY` and `GOOGLE_API_KEY` (never commit `.env`).

4. Start the server:

   ```bash
   python run.py
   ```

   Open `http://localhost:8000` in your browser and click **Try Call**.

## Tests

```bash
pytest -v
```
