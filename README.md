# Alderbrook Clinic — Voice Appointment Desk

Real-time clinic voice receptionist (**Claire**) paired with a live appointment dashboard. Callers speak directly from the browser—identified only by their spoken phone number—to check availability, book, and cancel appointments.

---

## Architecture

```mermaid
flowchart LR
    Mic["Browser Mic (16 kHz PCM16)"] -->|WS /ws/call| VAD["Silero VAD"]
    VAD --> STT["ElevenLabs STT (scribe_v2_realtime)"]
    STT --> LLM["Gemini 3.5 Flash"]
    LLM -->|Function Calls| DB[("SQLite (clinic.db)")]
    DB -->|SSE /api/events| UI["Live Dashboard"]
    LLM --> TTS["ElevenLabs TTS (eleven_turbo_v2_5)"]
    TTS -->|PCM16 Audio| Speaker["Browser Speaker"]
```

---

## Call Flow

```mermaid
sequenceDiagram
    participant C as Caller (Browser)
    participant A as Claire (Pipecat + Gemini)
    participant D as SQLite & Dashboard

    C->>A: Gives spoken phone number & asks for open slots
    A->>D: check_doctor_availability()
    D-->>A: Open slots
    A-->>C: Offers available times & reads phone number back
    C->>A: Confirms phone number & picks slot
    A->>D: book_appointment() / cancel_appointment()
    D-->>C: Live confirmation card + updated dashboard via SSE
```

---

## Stack

| Component | Model / Tool |
|---|---|
| **Pipeline** | Pipecat (`FastAPIWebsocketTransport` + `SileroVADAnalyzer`) |
| **Speech-to-Text** | ElevenLabs (`scribe_v2_realtime`) |
| **LLM** | **Google Gemini (`gemini-3.5-flash`)** |
| **Text-to-Speech** | ElevenLabs (`eleven_turbo_v2_5`) |
| **Backend & UI** | FastAPI, SQLite, SSE, Vanilla JS + Web Audio |

---

## Quick Start

```bash
git clone https://github.com/26Utkarsh/Alderbrook-AI-Reception.git
cd Alderbrook-AI-Reception

python -m venv .venv
# Windows: .\.venv\Scripts\Activate.ps1  |  macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # Add ELEVENLABS_API_KEY and GOOGLE_API_KEY

python run.py
```

Open **`http://localhost:8000`** and click **Try Call**.

## Tests

```bash
pytest -v
```
