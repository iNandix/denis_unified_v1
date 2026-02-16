from typing import TypedDict, Literal

class DeliveryTextDeltaV1(TypedDict):
    request_id: str
    text_delta: str
    is_final: bool
    sequence: int

class DeliveryInterruptV1(TypedDict):
    request_id: str
    reason: str

class RenderTextDeltaV1(TypedDict):
    request_id: str
    text_delta: str
    sequence: int

class RenderVoiceDeltaV1(TypedDict):
    request_id: str
    audio_chunk_b64: str
    format: Literal["wav"]
    sample_rate: int
    sequence: int

class RenderVoiceCancelledV1(TypedDict):
    request_id: str
    reason: str