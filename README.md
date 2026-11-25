# Alderbrook Clinic — Voice Appointment Desk

A real-time voice appointment booking system featuring **Claire**, Alderbrook Clinic's AI receptionist, paired with a live reception dashboard. Callers speak directly from the browser—no login, caller-ID, or OTP required—to check doctor availability, book an open slot, or cancel an existing appointment using only their spoken phone number.

---

## How It Works

```text
Browser Mic (Web Audio, 16 kHz PCM16)
  │
  ▼  WebSocket (/ws/call)
FastAPIWebsocketTransport + BrowserAudioSerializer
  │
  ├──▶ Silero VAD (stop_secs=0.25) ──▶ ElevenLabs Realtime STT (scribe_v2_realtime)
  │                                            │
  │                                            ▼  User Transcript
  │                                    Google Gemini LLM (gemini-3.5-flash)
  │                                      ├─ check_doctor_availability()
  │                                      ├─ book_appointment()      ──▶ SQLite (clinic.db)
  │                                      └─ cancel_appointment()    ──▶ SSE (/api/events)
  │                                            │
  │                                            ▼  Spoken Reply
  └──◀ Browser Audio Playback ◀── ElevenLabs TTS (eleven_turbo_v2_5)
```

1. **Audio Capture & Transport (`frontend/audio.js`, `backend/serializer.py`)**: The browser records microphone input via Web Audio, linearly resamples from the hardware rate to 16 kHz mono PCM16, and streams raw binary frames over `/ws/call`. `BrowserAudioSerializer` bridges binary audio frames and JSON control/transcript messages between the browser and Pipecat.
2. **Turn Detection & Speech-to-Text (`backend/pipeline.py`)**: `SileroVADAnalyzer` (configured on `LLMUserAggregatorParams`) detects when the caller starts and stops speaking, enabling barge-in interruptions and manual commit triggers for `ElevenLabsRealtimeSTTService` (`scribe_v2_realtime`). Clinic and doctor names are passed as `keyterms` alongside `filter_background_audio=True` for cleaner recognition.
3. **LLM & Tool Execution (`backend/pipeline.py`, `backend/tools.py`)**: **Google Gemini (`gemini-3.5-flash`)** serves as the conversational LLM. It follows strict clinic guardrails—always checking live slots before quoting times, reading the caller's phone number back for verbal confirmation before booking or cancelling, and keeping responses short and natural for speech.
4. **Voice Synthesis & Real-Time Dashboard (`backend/server.py`, `frontend/app.js`)**: Responses stream through `ElevenLabsTTSService` (`eleven_turbo_v2_5`) back to the browser's audio queue. Any booking or cancellation emits an event to both the active call modal (showing a confirmation card) and connected dashboards via Server-Sent Events (`/api/events`).

---

## Models & Tech Stack

| Layer | Technology / Model | Purpose |
|---|---|---|
| **Orchestration** | [Pipecat](https://github.com/pipecat-ai/pipecat) (`1.17.0+`) | Real-time voice pipeline, frame routing, interruption handling |
| **LLM** | **Google Gemini (`gemini-3.5-flash`)** | Conversational reasoning and function calling (`GEMINI_MODEL` in `.env`) |
| **Speech-to-Text** | ElevenLabs (`scribe_v2_realtime`) | Streaming WebSocket transcription with clinic `keyterms` |
| **Text-to-Speech** | ElevenLabs (`eleven_turbo_v2_5`) | Low-latency natural speech synthesis |
| **VAD** | Silero VAD | Local voice activity detection (`stop_secs=0.25`) |
| **Backend & DB** | FastAPI, Uvicorn, SQLite | HTTP/WebSocket/SSE server and persistent appointment store |
| **Frontend** | Vanilla HTML, CSS, JavaScript | Zero-build receptionist dashboard + phone call UI |

---

## Key Features

### Voice Tools (`backend/tools.py` & `backend/database.py`)
- **`check_doctor_availability`**: Filters open slots by doctor name, specialty, or date (`YYYY-MM-DD`), normalizing titles like `Dr.` / `Dr`.
- **`book_appointment`**: Validates and normalizes the spoken phone number (`normalize_phone`) and time format (`normalize_time`), marks the slot booked inside SQLite, and broadcasts `appointment_booked`.
- **`cancel_appointment`**: Looks up confirmed bookings by the caller's spoken phone number (asking to disambiguate by appointment ID if multiple active bookings exist), frees the slot, and broadcasts `appointment_cancelled`.

### Receptionist Dashboard (`frontend/`)
- **Schedule Panel**: Lists all doctors, specialties, rooms, and upcoming time slots with date tabs and an **Open only** toggle.
- **Appointments Panel**: Displays bookings with phone numbers, patient names, status badges (`confirmed` / `cancelled`), an **Active** filter, and flash highlights on live SSE updates.
- **Phone Call Modal (`Try Call`)**: Simulates a live call flow (`Ringing...` → `Connected` → `Call Ended`) with synthesized ringback/hangup tones, a live reactive audio waveform canvas, call timer, mute toggle, live caller/Claire transcript, and confirmation cards.

---

## Project Structure

```text
.
├── backend/
│   ├── config.py          # Loads .env settings (keys, models, DB path, sample rate)
│   ├── database.py        # SQLite schema, first-boot seeding, query/booking helpers
│   ├── pipeline.py        # Pipecat pipeline, Silero VAD, ElevenLabs STT/TTS, Gemini LLM
│   ├── serializer.py      # Binary PCM16 / JSON WebSocket frame serializer
│   ├── server.py          # FastAPI routes, SSE (/api/events), WebSocket (/ws/call)
│   └── tools.py           # Pipecat tool definitions and event emitters
├── frontend/
│   ├── index.html         # Dashboard and phone modal markup
│   ├── styles.css         # Warm-stone & forest-green minimal styling
│   ├── app.js             # Dashboard state, SSE listener, WebSocket call orchestration
│   └── audio.js           # Web Audio mic capture, resampling, ring tones, PCM16 playback
├── tests/
│   └── test_appointments.py
├── .env.example           # Environment variable template (no real secrets)
├── requirements.txt
└── run.py                 # Uvicorn entrypoint
```

---

## Setup & Running Locally

### Prerequisites
- Python **3.11+** (tested on Python 3.13)
- An **ElevenLabs API key** (with STT and TTS permissions; default voice `EXAVITQu4vr4xnSDxMaL` works on free tier)
- A **Google Gemini API key**

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/26Utkarsh/Alderbrook-AI-Reception.git
   cd Alderbrook-AI-Reception
   ```

2. **Create and activate a virtual environment**
   ```powershell
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   ```bash
   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and add your API keys:
   ```env
   ELEVENLABS_API_KEY=your_elevenlabs_key
   GOOGLE_API_KEY=your_google_gemini_key
   ```

   | Variable | Default | Description |
   |---|---|---|
   | `HOST` | `0.0.0.0` | Server bind address |
   | `PORT` | `8000` | Server port |
   | `DB_PATH` | `clinic.db` | SQLite database file path |
   | `ELEVENLABS_API_KEY` | — | Required ElevenLabs API key |
   | `ELEVENLABS_VOICE_ID` | `EXAVITQu4vr4xnSDxMaL` | ElevenLabs voice ID for Claire |
   | `GOOGLE_API_KEY` | — | Required Google Gemini API key |
   | `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model used for tool calling |

5. **Start the server**
   ```bash
   python run.py
   ```
   Open **`http://localhost:8000`** in your browser, allow microphone access, and click **Try Call**.

---

## API Endpoints

- `GET /` — Serves the reception dashboard
- `GET /api/health` — Returns `{ "status": "ok", "keys_configured": true|false }`
- `GET /api/dashboard` — Returns seeded/live doctors with slots and current appointments
- `GET /api/events` — Server-Sent Events stream pushing `appointment_booked` and `appointment_cancelled`
- `WS /ws/call` — Bidirectional 16 kHz PCM16 audio + JSON transcript/event stream

---

## Running Tests

Unit tests cover phone/time/doctor normalization, availability checks, double-booking protection, and appointment cancellation disambiguation:

```bash
pytest -v
```
