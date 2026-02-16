import asyncio
from typing import List, Dict, Any, Optional

from .pipecat_renderer import PipecatRendererNode
from .events_v1 import DeliveryTextDeltaV1, DeliveryInterruptV1


class DeliverySubgraph:
    def __init__(
        self,
        voice_enabled: bool = False,
        tts_provider: str = "none",
        piper_base_url: Optional[str] = "http://10.10.10.2:8005",
    ):
        self.events: List[Dict[str, Any]] = []
        self.renderer = PipecatRendererNode(
            emit_callback=self._emit,
            voice_enabled=voice_enabled,
            tts_provider=tts_provider,
            piper_base_url=piper_base_url,
        )

    def _emit(self, event: Dict[str, Any]):
        self.events.append(event)

    async def handle_text_delta(
        self, delta: DeliveryTextDeltaV1
    ) -> List[Dict[str, Any]]:
        self.events = []
        request_id = delta["request_id"]

        # Trigger text processing + parallel voice
        await self.renderer.on_timeline_delta(delta)

        # Wait for all voice tasks to complete
        if request_id in self.renderer.voice_tasks:
            tasks = self.renderer.voice_tasks[request_id]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        # Small buffer for last events
        await asyncio.sleep(0.2)
        return self.events

    async def handle_interrupt(
        self, interrupt: DeliveryInterruptV1
    ) -> List[Dict[str, Any]]:
        self.events = []
        await self.renderer.on_interrupt(interrupt)
        return self.events

    def get_metrics(self, request_id: str) -> dict:
        """Get voice metrics for a request."""
        return self.renderer.get_metrics(request_id)
