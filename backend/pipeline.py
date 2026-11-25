import datetime
from typing import Awaitable, Callable

from fastapi import WebSocket
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMRunFrame,
    LLMTextFrame,
    OutputTransportMessageUrgentFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.elevenlabs.stt import CommitStrategy, ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from backend.config import settings
from backend.database import ClinicStore
from backend.serializer import BrowserAudioSerializer
from backend.tools import CLINIC_TOOLS, ClinicAppResources


SYSTEM_PROMPT = """You are Claire, the front-desk receptionist at Alderbrook Clinic.
You are speaking on a live phone call with a patient. Keep responses warm, concise, and natural for spoken conversation—no bullet points, markdown, or special characters.

Today's date is {today}.

Core rules you must follow on every call:
1. Identify the caller ONLY by the phone number they say out loud. Never ask for a login, account, or OTP.
2. Before calling book_appointment or cancel_appointment, you MUST read the phone number back to the caller digit by digit (or in clear groups) and get their verbal confirmation that it is correct.
3. Always call check_doctor_availability before offering or confirming open times so you only quote real slots.
4. When booking, confirm the doctor, date, time, and confirmed phone number clearly.
5. When cancelling, look up and cancel using the caller's confirmed phone number, then confirm the cancelled appointment details.
6. Handle availability checks, bookings, and cancellations naturally within a single conversation."""


class TranscriptForwarder(FrameProcessor):
    """Forwards user STT and assistant LLM text frames to the browser UI."""

    def __init__(self, role: str, **kwargs):
        super().__init__(**kwargs)
        self._role = role
        self._buffer: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InterruptionFrame) and self._role == "assistant":
            self._buffer.clear()
        elif self._role == "user" and isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if text:
                await self.push_frame(
                    OutputTransportMessageUrgentFrame(
                        message={"type": "transcript", "role": "user", "text": text}
                    ),
                    FrameDirection.DOWNSTREAM,
                )
        elif self._role == "assistant":
            if isinstance(frame, LLMTextFrame):
                self._buffer.append(frame.text)
            elif isinstance(frame, LLMFullResponseEndFrame):
                full_text = "".join(self._buffer).strip()
                self._buffer.clear()
                if full_text:
                    await self.push_frame(
                        OutputTransportMessageUrgentFrame(
                            message={
                                "type": "transcript",
                                "role": "assistant",
                                "text": full_text,
                            }
                        ),
                        FrameDirection.DOWNSTREAM,
                    )

        await self.push_frame(frame, direction)


async def run_voice_session(
    websocket: WebSocket,
    store: ClinicStore,
    broadcast_dashboard_event: Callable[[dict], Awaitable[None]],
) -> None:
    if not settings.elevenlabs_api_key or not settings.google_api_key:
        await websocket.send_json(
            {
                "type": "error",
                "message": "Missing ELEVENLABS_API_KEY or GOOGLE_API_KEY in .env.",
            }
        )
        await websocket.close(code=1011)
        return

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=settings.sample_rate,
            audio_out_sample_rate=settings.sample_rate,
            serializer=BrowserAudioSerializer(sample_rate=settings.sample_rate),
        ),
    )

    stt = ElevenLabsRealtimeSTTService(
        api_key=settings.elevenlabs_api_key,
        sample_rate=settings.sample_rate,
        commit_strategy=CommitStrategy.MANUAL,
        settings=ElevenLabsRealtimeSTTService.Settings(
            model="scribe_v2_realtime",
            keyterms=[
                "Alderbrook Clinic",
                "Dr. Maya Patel",
                "Dr. Hannah Lin",
                "Dr. Carlos Garcia",
                "Dr. Samuel Okafor",
            ],
            filter_background_audio=True,
        ),
    )

    llm = GoogleLLMService(
        api_key=settings.google_api_key,
        retry_on_timeout=True,
        retry_timeout_secs=8.0,
        stream_idle_timeout_secs=25.0,
        settings=GoogleLLMService.Settings(
            model=settings.gemini_model,
            system_instruction=SYSTEM_PROMPT.format(
                today=datetime.date.today().isoformat()
            ),
        ),
    )

    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        sample_rate=settings.sample_rate,
        settings=ElevenLabsTTSService.Settings(
            voice=settings.elevenlabs_voice_id,
            model="eleven_turbo_v2_5",
            stability=0.55,
            similarity_boost=0.8,
            use_speaker_boost=True,
        ),
    )

    context = LLMContext(tools=CLINIC_TOOLS)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.25)),
        ),
    )

    user_transcript = TranscriptForwarder(role="user")
    assistant_transcript = TranscriptForwarder(role="assistant")

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_transcript,
            user_aggregator,
            llm,
            assistant_transcript,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    async def emit_call_and_dashboard_event(payload: dict) -> None:
        await broadcast_dashboard_event(payload)
        await task.queue_frame(
            OutputTransportMessageUrgentFrame(message=payload)
        )

    resources = ClinicAppResources(
        store=store,
        emit_event=emit_call_and_dashboard_event,
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=settings.sample_rate,
            audio_out_sample_rate=settings.sample_rate,
            allow_interruptions=True,
            enable_metrics=True,
        ),
        app_resources=resources,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _ws):
        logger.info("Voice call connected")
        context.add_message(
            {
                "role": "user",
                "content": "Greet the caller warmly as Claire from Alderbrook Clinic reception and ask how you can help today.",
            }
        )
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _ws):
        logger.info("Voice call disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
