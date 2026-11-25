<div align="center">

# Alderbrook Clinic — Voice Appointment Desk

Real-time AI clinic receptionist (**Claire**) paired with a live reception dashboard.  
Identify callers by spoken phone number alone—check availability, book slots, and cancel appointments end to end.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Pipecat](https://img.shields.io/badge/Pipeline-Pipecat_1.17-186049?style=flat-square)
![Gemini](https://img.shields.io/badge/LLM-Gemini_3.5_Flash-4285F4?style=flat-square&logo=googlegemini&logoColor=white)
![ElevenLabs](https://img.shields.io/badge/Voice-ElevenLabs_STT_%2B_TTS-111111?style=flat-square)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI_%2B_SQLite-009688?style=flat-square&logo=fastapi&logoColor=white)

</div>

---

## Architecture Graphic

```mermaid
flowchart LR
    subgraph Browser["Frontend (Vanilla JS + Web Audio)"]
        Mic["Mic Capture (16 kHz PCM16)"]
        UI["Live Schedule & Appointments"]
        Phone["Try Call Phone Sheet"]
    end

    subgraph Pipeline["Pipecat Voice Pipeline (backend/pipeline.py)"]
        WS["FastAPI WebSocket (/ws/call)"]
        VAD["Silero VAD (stop_secs=0.25)"]
        STT["ElevenLabs STT (scribe_v2_realtime)"]
        LLM["Gemini 3.5 Flash (Function Calling)"]
        TTS["ElevenLabs TTS (eleven_turbo_v2_5)"]
    end

    subgraph Data["Persistence & Realtime Sync"]
        DB[("SQLite (clinic.db)")]
        SSE["SSE Stream (/api/events)"]
    end

    Mic -->|Binary PCM16| WS
    WS --> VAD --> STT --> LLM
    LLM <-->|check / book / cancel| DB
    DB --> SSE --> UI
    LLM --> TTS --> WS -->|PCM16 Audio + Transcripts| Phone
```

---

## Call & Booking Workflow

```mermaid
sequenceDiagram
    autonumber
    participant Caller as Caller (Browser Mic)
    participant Voice as Pipecat + ElevenLabs STT/TTS
    participant LLM as Gemini 3.5 Flash
    participant Store as SQLite & Live Dashboard

    Caller->>Voice: Clicks Try Call & speaks request
    Voice->>LLM: Real-time transcript (scribe_v2_realtime)
    LLM->>Store: check_doctor_availability(doctor, date)
    Store-->>LLM: Open time slots
    LLM->>Voice: Reads open slots & asks for confirmation
    Voice-->>Caller: Synthesized speech (eleven_turbo_v2_5)

    Caller->>Voice: Confirms spoken phone number & picks slot
    Voice->>LLM: Confirmed transcript
    LLM->>Store: book_appointment() / cancel_appointment()
    Store-->>Caller: Confirmation card in phone UI + live SSE row flash
```

---

## Tech Stack

| Layer | Technology | Model / Role |
|---|---|---|
| **Voice Framework** | Pipecat (`pipecat-ai`) | Pipeline orchestration, interruption handling, WebSocket transport |
| **Speech-to-Text** | ElevenLabs Realtime STT | `scribe_v2_realtime` with clinic `keyterms` & background noise filtering |
| **LLM** | **Google Gemini** | **`gemini-3.5-flash`** for dialogue & tool calling (`GEMINI_MODEL`) |
| **Text-to-Speech** | ElevenLabs TTS | `eleven_turbo_v2_5` streaming PCM16 audio (`EXAVITQu4vr4xnSDxMaL`) |
| **Turn Detection** | Silero VAD | Local voice activity detection (`stop_secs=0.25`) |
| **API & Storage** | FastAPI, Uvicorn, SQLite | REST, `/ws/call` WebSocket, `/api/events` SSE, `clinic.db` |
| **Frontend** | HTML, CSS, Vanilla JS | Web Audio resampling, reactive waveform, zero-build dashboard |

---

## Voice Tools & API

| Tool / Endpoint | Purpose | Key Behavior |
|---|---|---|
| `check_doctor_availability` | Query open doctor slots | Matches doctor name, specialty, or `YYYY-MM-DD` date |
| `book_appointment` | Reserve an open slot | Requires verbal phone confirmation; prevents double-booking |
| `cancel_appointment` | Cancel an active booking | Matches spoken phone number; frees slot & disambiguates duplicates |
| `GET /api/dashboard` | Initial UI state | Returns 4 seeded doctors with slots and appointments |
| `GET /api/events` | Real-time UI sync | SSE stream pushing `appointment_booked` & `appointment_cancelled` |
| `WS /ws/call` | Live voice session | Bidirectional 16 kHz PCM16 audio + JSON transcript/event frames |

---

## Clone Guide

```bash
git clone https://github.com/26Utkarsh/Alderbrook-AI-Reception.git
cd Alderbrook-AI-Reception
```

---

## Setup Guide

### 1. Create a Virtual Environment

| OS | Command |
|---|---|
| **Windows (PowerShell)** | `python -m venv .venv; .\.venv\Scripts\Activate.ps1` |
| **macOS / Linux** | `python3 -m venv .venv && source .venv/bin/activate` |

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Add your keys inside `.env` (never commit `.env`):

| Variable | Required | Default | Description |
|---|---|---|---|
| `ELEVENLABS_API_KEY` | Yes | — | ElevenLabs API key (STT + TTS) |
| `GOOGLE_API_KEY` | Yes | — | Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini-3.5-flash` | Gemini model for reasoning & tools |
| `ELEVENLABS_VOICE_ID` | No | `EXAVITQu4vr4xnSDxMaL` | ElevenLabs voice ID for Claire |
| `PORT` | No | `8000` | FastAPI server port |

### 4. Run the App & Tests

```bash
# Run unit tests
pytest -v

# Start the server
python run.py
```

Open **`http://localhost:8000`**, allow microphone access, and click **Try Call**.
