"""Advanced hedging: parallel requests with smart cancellation."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, AsyncIterator

from denis_unified_v1.observability.metrics import inference_engine_selection
from denis_unified_v1.observability.tracing import get_tracer

tracer = get_tracer()


@dataclass
class HedgedRequest:
    """Configuration for a hedged request."""
    
    primary_engine: str
    backup_engines: List[str]
    hedge_delay_ms: float = 100  # Delay before starting backup
    max_parallel: int = 2
    cancel_on_first_token: bool = True


@dataclass
class HedgedResult:
    """Result from hedged execution."""
    
    winner_engine: str
    result: Any
    latency_ms: float
    hedged_count: int
    cancelled_engines: List[str]
    all_latencies: Dict[str, float]


class HedgingExecutor:
    """Executes hedged requests with smart cancellation."""
    
    def __init__(self):
        self.active_hedges: Dict[str, List[asyncio.Task]] = {}
    
    async def execute_hedged(
        self,
        hedge_config: HedgedRequest,
        execute_fn: callable,
        messages: List[Dict],
        stream: bool = False,
        **kwargs,
    ) -> HedgedResult:
        """Execute request with hedging strategy."""
        with tracer.start_as_current_span("hedging.execute") as span:
            span.set_attribute("primary_engine", hedge_config.primary_engine)
            span.set_attribute("backup_count", len(hedge_config.backup_engines))
            
            start_time = time.time()
            tasks = []
            engine_tasks = {}
            
            # Start primary
            primary_task = asyncio.create_task(
                self._execute_with_tracking(
                    hedge_config.primary_engine,
                    execute_fn,
                    messages,
                    stream,
                    **kwargs,
                )
            )
            tasks.append(primary_task)
            engine_tasks[hedge_config.primary_engine] = primary_task
            
            # Wait for hedge delay
            if hedge_config.hedge_delay_ms > 0:
                try:
                    result = await asyncio.wait_for(
                        primary_task,
                        timeout=hedge_config.hedge_delay_ms / 1000,
                    )
                    # Primary completed within delay
                    return HedgedResult(
                        winner_engine=hedge_config.primary_engine,
                        result=result["result"],
                        latency_ms=(time.time() - start_time) * 1000,
                        hedged_count=0,
                        cancelled_engines=[],
                        all_latencies={
                            hedge_config.primary_engine: result["latency_ms"]
                        },
                    )
                except asyncio.TimeoutError:
                    pass  # Continue to hedging
            
            # Start backup engines
            backup_count = min(
                len(hedge_config.backup_engines),
                hedge_config.max_parallel - 1,
            )
            
            for backup_engine in hedge_config.backup_engines[:backup_count]:
                backup_task = asyncio.create_task(
                    self._execute_with_tracking(
                        backup_engine,
                        execute_fn,
                        messages,
                        stream,
                        **kwargs,
                    )
                )
                tasks.append(backup_task)
                engine_tasks[backup_engine] = backup_task
            
            span.set_attribute("hedged_count", len(tasks) - 1)
            
            # Wait for first completion
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            # Get winner
            winner_task = list(done)[0]
            winner_result = await winner_task
            winner_engine = winner_result["engine_id"]
            
            # Cancel remaining tasks
            cancelled = []
            for engine_id, task in engine_tasks.items():
                if task in pending:
                    task.cancel()
                    cancelled.append(engine_id)
            
            # Wait for cancellations
            if pending:
                await asyncio.wait(pending, timeout=0.1)
            
            # Collect all latencies
            all_latencies = {}
            for engine_id, task in engine_tasks.items():
                if task.done() and not task.cancelled():
                    try:
                        result = task.result()
                        all_latencies[engine_id] = result["latency_ms"]
                    except Exception:
                        pass
            
            total_latency = (time.time() - start_time) * 1000
            
            span.set_attribute("winner_engine", winner_engine)
            span.set_attribute("cancelled_count", len(cancelled))
            
            return HedgedResult(
                winner_engine=winner_engine,
                result=winner_result["result"],
                latency_ms=total_latency,
                hedged_count=len(tasks) - 1,
                cancelled_engines=cancelled,
                all_latencies=all_latencies,
            )
    
    async def _execute_with_tracking(
        self,
        engine_id: str,
        execute_fn: callable,
        messages: List[Dict],
        stream: bool,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute with latency tracking."""
        start = time.time()
        
        try:
            result = await execute_fn(
                engine_id=engine_id,
                messages=messages,
                stream=stream,
                **kwargs,
            )
            
            latency_ms = (time.time() - start) * 1000
            
            return {
                "engine_id": engine_id,
                "result": result,
                "latency_ms": latency_ms,
                "success": True,
            }
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            return {
                "engine_id": engine_id,
                "result": {"error": str(e)},
                "latency_ms": latency_ms,
                "success": False,
            }
    
    async def execute_hedged_streaming(
        self,
        hedge_config: HedgedRequest,
        execute_fn: callable,
        messages: List[Dict],
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Execute hedged request with streaming support."""
        with tracer.start_as_current_span("hedging.execute_streaming"):
            start_time = time.time()
            
            # Create queues for each engine
            queues = {
                hedge_config.primary_engine: asyncio.Queue(),
            }
            
            for backup in hedge_config.backup_engines[:hedge_config.max_parallel - 1]:
                queues[backup] = asyncio.Queue()
            
            # Start all engines
            tasks = []
            for engine_id, queue in queues.items():
                task = asyncio.create_task(
                    self._stream_to_queue(
                        engine_id,
                        execute_fn,
                        messages,
                        queue,
                        **kwargs,
                    )
                )
                tasks.append(task)
            
            # Wait for first token from any engine
            winner_engine = None
            winner_queue = None
            
            while not winner_engine:
                for engine_id, queue in queues.items():
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=0.01)
                        if item is not None:
                            winner_engine = engine_id
                            winner_queue = queue
                            
                            # Yield first token
                            yield {
                                "engine_id": winner_engine,
                                "delta": item,
                                "hedged": True,
                            }
                            break
                    except asyncio.TimeoutError:
                        continue
            
            # Cancel losers
            for task in tasks:
                if task not in [t for t in tasks if not t.done()]:
                    continue
                task.cancel()
            
            # Stream remaining tokens from winner
            while True:
                try:
                    item = await asyncio.wait_for(winner_queue.get(), timeout=1.0)
                    if item is None:  # End marker
                        break
                    yield {
                        "engine_id": winner_engine,
                        "delta": item,
                        "hedged": False,
                    }
                except asyncio.TimeoutError:
                    break
            
            # Final metadata
            yield {
                "engine_id": winner_engine,
                "metadata": {
                    "total_latency_ms": (time.time() - start_time) * 1000,
                    "hedged_count": len(queues) - 1,
                },
            }
    
    async def _stream_to_queue(
        self,
        engine_id: str,
        execute_fn: callable,
        messages: List[Dict],
        queue: asyncio.Queue,
        **kwargs,
    ) -> None:
        """Stream results to queue."""
        try:
            async for chunk in execute_fn(
                engine_id=engine_id,
                messages=messages,
                stream=True,
                **kwargs,
            ):
                await queue.put(chunk)
            
            # End marker
            await queue.put(None)
        except asyncio.CancelledError:
            await queue.put(None)
        except Exception as e:
            await queue.put({"error": str(e)})
            await queue.put(None)


class AdaptiveHedgingPolicy:
    """Learns when to hedge based on historical performance."""
    
    def __init__(self):
        self.engine_p95_latencies: Dict[str, float] = {}
        self.engine_failure_rates: Dict[str, float] = {}
        self.hedge_threshold_ms = 200  # Hedge if p95 > this
        self.failure_threshold = 0.05  # Hedge if failure rate > 5%
    
    def should_hedge(
        self,
        primary_engine: str,
        class_key: str,
    ) -> bool:
        """Decide if hedging is beneficial."""
        # Check latency
        p95 = self.engine_p95_latencies.get(primary_engine, 0)
        if p95 > self.hedge_threshold_ms:
            return True
        
        # Check failure rate
        failure_rate = self.engine_failure_rates.get(primary_engine, 0)
        if failure_rate > self.failure_threshold:
            return True
        
        return False
    
    def update_stats(
        self,
        engine_id: str,
        latency_ms: float,
        success: bool,
    ) -> None:
        """Update engine statistics."""
        # Simple EMA for p95 (approximation)
        current_p95 = self.engine_p95_latencies.get(engine_id, latency_ms)
        self.engine_p95_latencies[engine_id] = (
            0.95 * current_p95 + 0.05 * latency_ms
        )
        
        # EMA for failure rate
        current_failure = self.engine_failure_rates.get(engine_id, 0)
        new_failure = 0.0 if success else 1.0
        self.engine_failure_rates[engine_id] = (
            0.95 * current_failure + 0.05 * new_failure
        )
    
    def get_hedge_config(
        self,
        primary_engine: str,
        available_engines: List[str],
    ) -> Optional[HedgedRequest]:
        """Get hedging configuration if needed."""
        if not self.should_hedge(primary_engine, ""):
            return None
        
        # Select backup engines (exclude primary)
        backups = [e for e in available_engines if e != primary_engine]
        
        if not backups:
            return None
        
        # Calculate optimal hedge delay based on p95
        p95 = self.engine_p95_latencies.get(primary_engine, 100)
        hedge_delay = min(p95 * 0.5, 150)  # 50% of p95, max 150ms
        
        return HedgedRequest(
            primary_engine=primary_engine,
            backup_engines=backups,
            hedge_delay_ms=hedge_delay,
            max_parallel=2,
        )
