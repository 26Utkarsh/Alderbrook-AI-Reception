import json
from typing import Any, Optional

from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer


class BrowserAudioSerializer(FrameSerializer):
    """Bridges raw 16kHz PCM16 browser WebSocket audio with Pipecat frames."""

    def __init__(self, sample_rate: int = 16000):
        super().__init__()
        self._sample_rate = sample_rate

    async def setup(self, frame: Any) -> None:
        in_rate = getattr(frame, "audio_in_sample_rate", None)
        if in_rate:
            self._sample_rate = in_rate

    async def serialize(self, frame: Frame) -> Optional[str | bytes]:
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        if isinstance(frame, (OutputTransportMessageFrame, OutputTransportMessageUrgentFrame)):
            return json.dumps(frame.message)
        if isinstance(frame, InterruptionFrame):
            return json.dumps({"type": "clear_audio"})
        return None

    async def deserialize(self, data: str | bytes) -> Optional[Frame]:
        if isinstance(data, bytes):
            if not data:
                return None
            return InputAudioRawFrame(
                audio=data,
                sample_rate=self._sample_rate,
                num_channels=1,
            )
        return None
