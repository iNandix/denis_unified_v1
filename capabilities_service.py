"""Capabilities Service - Unified system integration with collectors and snapshot aggregation."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import threading
from pathlib import Path
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class CapabilityStatus(Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


@dataclass
class Evidence:
    source: str
    timestamp: float
    confidence: float
    data: Dict[str, Any]
    error: Optional[str] = None


@dataclass
class CapabilitySnapshot:
    """Unified CapabilitySnapshot v1 structure."""
    id: str
    category: str
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    confidence: float = 0.0
    evidence: List[Evidence] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    last_seen_utc: float = field(default_factory=time.time)
    depends_on: List[str] = field(default_factory=list)
    source_weights: Dict[str, float] = field(default_factory=dict)
    executable_actions: List[str] = field(default_factory=list)
    version: str = "v1"


class CapabilityCollector(ABC):
    """Abstract base for capability collectors."""

    @abstractmethod
    async def collect(self) -> Dict[str, CapabilitySnapshot]:
        """Collect capabilities from source. Always return dict, even if empty."""
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Get collector source name."""
        pass


class ArtifactCollector(CapabilityCollector):
    """Collect capabilities from artifacts directory (phase completions, smoke results)."""

    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir

    def get_source_name(self) -> str:
        return "artifacts"

    async def collect(self) -> Dict[str, CapabilitySnapshot]:
        capabilities = {}

        try:
            # Phase completion artifacts
            phase_files = {
                "phase0_integration": "phase11_preflight.json",
                "phase1_integration": "level3_metacognitive_smoke.json",
                "phase5_integration": "phase5_orchestration_smoke.json",
                "phase6_integration": "phase6_api_smoke.json",
                "phase7_integration": "phase7_inference_router_smoke.json",
                "phase8_integration": "phase8_voice_smoke.json",
                "phase9_integration": "phase9_memory_smoke.json",
                "phase10_integration": "phase10_self_model_smoke.json",
            }

            for cap_id, filename in phase_files.items():
                artifact_path = self.artifacts_dir / filename
                if artifact_path.exists():
                    try:
                        with artifact_path.open() as f:
                            data = json.load(f)
                        status_str = data.get("status", "unknown")
                        status = CapabilityStatus(status_str.upper()) if status_str.upper() in CapabilityStatus.__members__ else CapabilityStatus.UNKNOWN
                        ok = data.get("ok", False)
                        confidence = 1.0 if ok else 0.5

                        evidence = Evidence(
                            source="artifacts",
                            timestamp=data.get("timestamp_utc", time.time()),
                            confidence=confidence,
                            data={"artifact_path": str(artifact_path), "results": data}
                        )

                        snapshot = CapabilitySnapshot(
                            id=cap_id,
                            category="system_integration",
                            status=status,
                            confidence=confidence,
                            evidence=[evidence],
                            metrics={"artifact_ok": ok, "phase_status": status_str},
                            source_weights={"artifacts": 1.0}
                        )
                        capabilities[cap_id] = snapshot
                    except Exception as e:
                        logger.warning(f"Failed to load artifact {filename}: {e}")
                else:
                    # Phase not completed
                    snapshot = CapabilitySnapshot(
                        id=cap_id,
                        category="system_integration",
                        status=CapabilityStatus.SKIPPED,
                        confidence=0.0,
                        evidence=[Evidence(
                            source="artifacts",
                            timestamp=time.time(),
                            confidence=0.0,
                            data={"missing_artifact": filename},
                            error=f"Artifact {filename} not found"
                        )],
                        source_weights={"artifacts": 0.0}
                    )
                    capabilities[cap_id] = snapshot

            # Smoke test results
            smoke_files = list(self.artifacts_dir.glob("*smoke.json"))
            for smoke_file in smoke_files:
                try:
                    with smoke_file.open() as f:
                        data = json.load(f)
                    cap_id = f"smoke_{smoke_file.stem}"
                    ok = data.get("ok", False)
                    status = CapabilityStatus.ACTIVE if ok else CapabilityStatus.DEGRADED

                    evidence = Evidence(
                        source="artifacts",
                        timestamp=time.time(),
                        confidence=1.0 if ok else 0.3,
                        data={"smoke_results": data}
                    )

                    snapshot = CapabilitySnapshot(
                        id=cap_id,
                        category="testing",
                        status=status,
                        confidence=1.0 if ok else 0.3,
                        evidence=[evidence],
                        metrics={"smoke_passed": ok},
                        source_weights={"artifacts": 1.0}
                    )
                    capabilities[cap_id] = snapshot
                except Exception as e:
                    logger.warning(f"Failed to load smoke {smoke_file}: {e}")

        except Exception as e:
            logger.error(f"ArtifactCollector error: {e}")

        return capabilities


class BackendProbeCollector(CapabilityCollector):
    """Probe backend endpoints for health and latency."""

    def __init__(self, base_url: str = "http://localhost:8085"):
        self.base_url = base_url

    def get_source_name(self) -> str:
        return "backends"

    async def collect(self) -> Dict[str, CapabilitySnapshot]:
        capabilities = {}

        probes = {
            "metacognitive_api": "/metacognitive/status",
            "memory_backend": "/memory/status",
            "inference_router": "/inference/status",
            "voice_pipeline": "/voice/health",
            "graph_database": "/graph/health",
        }

        for cap_id, endpoint in probes.items():
            try:
                import httpx
                start_time = time.time()
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{self.base_url}{endpoint}")
                latency_ms = (time.time() - start_time) * 1000

                status = CapabilityStatus.ACTIVE if resp.status_code == 200 else CapabilityStatus.DEGRADED
                confidence = 1.0 if resp.status_code == 200 else 0.2

                evidence = Evidence(
                    source="backends",
                    timestamp=time.time(),
                    confidence=confidence,
                    data={"endpoint": endpoint, "status_code": resp.status_code, "latency_ms": latency_ms}
                )

                snapshot = CapabilitySnapshot(
                    id=cap_id,
                    category="backend_health",
                    status=status,
                    confidence=confidence,
                    evidence=[evidence],
                    metrics={"latency_ms": latency_ms, "http_status": resp.status_code},
                    source_weights={"backends": 1.0}
                )
                capabilities[cap_id] = snapshot

            except Exception as e:
                snapshot = CapabilitySnapshot(
                    id=cap_id,
                    category="backend_health",
                    status=CapabilityStatus.SKIPPED,
                    confidence=0.0,
                    evidence=[Evidence(
                        source="backends",
                        timestamp=time.time(),
                        confidence=0.0,
                        data={"endpoint": endpoint},
                        error=str(e)
                    )],
                    metrics={"error": str(e)},
                    source_weights={"backends": 0.0}
                )
                capabilities[cap_id] = snapshot

        return capabilities


class GraphCollector(CapabilityCollector):
    """Collect capabilities from Neo4j/IDE Graph."""

    def get_source_name(self) -> str:
        return "graph"

    async def collect(self) -> Dict[str, CapabilitySnapshot]:
        capabilities = {}

        try:
            # Try IDE Graph first
            from denis_unified_v1.tools.ide_graph import ide_graph_client
            client = ide_graph_client.IDEGraphClient()

            # Query services
            services = await client.get_services()
            for service in services:
                cap_id = f"service_{service['id']}"
                status = CapabilityStatus.ACTIVE if service.get("healthy", False) else CapabilityStatus.DEGRADED

                evidence = Evidence(
                    source="graph",
                    timestamp=time.time(),
                    confidence=0.8,
                    data={"service_info": service}
                )

                snapshot = CapabilitySnapshot(
                    id=cap_id,
                    category="graph_services",
                    status=status,
                    confidence=0.8,
                    evidence=[evidence],
                    metrics={"healthy": service.get("healthy", False)},
                    source_weights={"graph": 1.0}
                )
                capabilities[cap_id] = snapshot

        except Exception as e:
            logger.warning(f"IDE Graph collection failed: {e}")

        try:
            # Try Neo4j
            from denis_unified_v1.metagraph.active_metagraph import get_metagraph_client
            client = get_metagraph_client()
            if client:
                # Query tools
                tools_query = "MATCH (t:Tool) RETURN t.name as name, t.success_rate as success_rate LIMIT 10"
                tools_result = client.query(tools_query)
                for record in tools_result:
                    cap_id = f"tool_{record['name']}"
                    status = CapabilityStatus.ACTIVE
                    confidence = record.get("success_rate", 0.5)

                    evidence = Evidence(
                        source="graph",
                        timestamp=time.time(),
                        confidence=confidence,
                        data={"tool_info": dict(record)}
                    )

                    snapshot = CapabilitySnapshot(
                        id=cap_id,
                        category="graph_tools",
                        status=status,
                        confidence=confidence,
                        evidence=[evidence],
                        metrics={"success_rate": record.get("success_rate", 0)},
                        source_weights={"graph": 1.0}
                    )
                    capabilities[cap_id] = snapshot

                # Query patterns
                patterns_query = "MATCH (p:Pattern) RETURN p.id as id, p.confidence as confidence LIMIT 10"
                patterns_result = client.query(patterns_query)
                for record in patterns_result:
                    cap_id = f"pattern_{record['id']}"
                    confidence = record.get("confidence", 0.5)

                    evidence = Evidence(
                        source="graph",
                        timestamp=time.time(),
                        confidence=confidence,
                        data={"pattern_info": dict(record)}
                    )

                    snapshot = CapabilitySnapshot(
                        id=cap_id,
                        category="graph_patterns",
                        status=CapabilityStatus.ACTIVE,
                        confidence=confidence,
                        evidence=[evidence],
                        metrics={"confidence": confidence},
                        source_weights={"graph": 1.0}
                    )
                    capabilities[cap_id] = snapshot

        except Exception as e:
            logger.warning(f"Neo4j collection failed: {e}")

        if not capabilities:
            # If no graph data, mark as skipped
            snapshot = CapabilitySnapshot(
                id="graph_integration",
                category="graph_health",
                status=CapabilityStatus.SKIPPED,
                confidence=0.0,
                evidence=[Evidence(
                    source="graph",
                    timestamp=time.time(),
                    confidence=0.0,
                    data={},
                    error="No graph data available"
                )],
                source_weights={"graph": 0.0}
            )
            capabilities["graph_integration"] = snapshot

        return capabilities


class WorkerCollector(CapabilityCollector):
    """Collect executable capabilities from workers/queues."""

    def get_source_name(self) -> str:
        return "workers"

    async def collect(self) -> Dict[str, CapabilitySnapshot]:
        capabilities = {}

        # Check for available workers
        workers_to_check = {
            "inference_worker": "inference_router",
            "memory_worker": "memory_backend",
            "voice_worker": "voice_pipeline",
            "tool_worker": "tool_executor",
        }

        for worker_id, backend_name in workers_to_check.items():
            try:
                # Try to import and check worker availability
                if worker_id == "inference_worker":
                    from denis_unified_v1.inference import get_inference_router
                    worker = get_inference_router()
                    available = worker is not None
                elif worker_id == "memory_worker":
                    from denis_unified_v1.memory.backends import get_memory_backend
                    worker = get_memory_backend()
                    available = worker is not None
                elif worker_id == "voice_worker":
                    from denis_unified_v1.voice import get_voice_pipeline
                    worker = get_voice_pipeline()
                    available = worker is not None
                elif worker_id == "tool_worker":
                    from denis_unified_v1.orchestration.tool_executor import get_tool_executor
                    worker = get_tool_executor()
                    available = worker is not None
                else:
                    available = False

                status = CapabilityStatus.ACTIVE if available else CapabilityStatus.SKIPPED
                confidence = 1.0 if available else 0.0

                evidence = Evidence(
                    source="workers",
                    timestamp=time.time(),
                    confidence=confidence,
                    data={"worker_id": worker_id, "backend": backend_name, "available": available}
                )

                snapshot = CapabilitySnapshot(
                    id=worker_id,
                    category="executable_workers",
                    status=status,
                    confidence=confidence,
                    evidence=[evidence],
                    executable_actions=[f"execute_{backend_name}"],
                    metrics={"worker_available": available},
                    source_weights={"workers": 1.0}
                )
                capabilities[worker_id] = snapshot

            except Exception as e:
                snapshot = CapabilitySnapshot(
                    id=worker_id,
                    category="executable_workers",
                    status=CapabilityStatus.SKIPPED,
                    confidence=0.0,
                    evidence=[Evidence(
                        source="workers",
                        timestamp=time.time(),
                        confidence=0.0,
                        data={"worker_id": worker_id, "backend": backend_name},
                        error=str(e)
                    )],
                    source_weights={"workers": 0.0}
                )
                capabilities[worker_id] = snapshot

        return capabilities


class CapabilitiesService:
    """Unified capabilities service with collectors and aggregation."""

    def __init__(self):
        self.collectors: List[CapabilityCollector] = []
        self._cache: Optional[Dict[str, CapabilitySnapshot]] = None
        self._cache_timestamp = 0
        self._cache_ttl = 300  # 5 minutes
        self._lock = threading.RLock()

    def add_collector(self, collector: CapabilityCollector) -> None:
        self.collectors.append(collector)

    async def refresh_snapshot(self) -> Dict[str, CapabilitySnapshot]:
        """Refresh capabilities from all collectors."""
        with self._lock:
            logger.info("Refreshing capabilities snapshot")
            all_capabilities = {}

            # Collect from all sources
            for collector in self.collectors:
                try:
                    source_caps = await collector.collect()
                    for cap_id, snapshot in source_caps.items():
                        if cap_id not in all_capabilities:
                            all_capabilities[cap_id] = snapshot
                        else:
                            # Merge evidence from multiple sources
                            existing = all_capabilities[cap_id]
                            existing.evidence.extend(snapshot.evidence)
                            # Update source weights
                            for source, weight in snapshot.source_weights.items():
                                existing.source_weights[source] = existing.source_weights.get(source, 0) + weight
                            # Recalculate confidence based on sources
                            total_weight = sum(existing.source_weights.values())
                            if total_weight > 0:
                                existing.confidence = sum(
                                    ev.confidence * existing.source_weights.get(ev.source, 1)
                                    for ev in existing.evidence
                                ) / total_weight
                            # Update status based on evidence
                            if any(ev.error for ev in existing.evidence):
                                existing.status = CapabilityStatus.DEGRADED
                            elif all(ev.confidence > 0.5 for ev in existing.evidence):
                                existing.status = CapabilityStatus.ACTIVE
                except Exception as e:
                    logger.error(f"Collector {collector.get_source_name()} failed: {e}")

            self._cache = all_capabilities
            self._cache_timestamp = time.time()
            logger.info(f"Refreshed {len(all_capabilities)} capabilities")
            return all_capabilities

    def get_snapshot(self) -> Dict[str, CapabilitySnapshot]:
        """Get cached capabilities snapshot."""
        with self._lock:
            current_time = time.time()
            if self._cache is None or (current_time - self._cache_timestamp) > self._cache_ttl:
                # Cache expired, need refresh (but this is sync method, so return stale if available)
                if self._cache is None:
                    logger.warning("No cached capabilities available, call refresh_snapshot() first")
                    return {}
            return self._cache.copy()

    def query_snapshot(self, filters: Dict[str, Any]) -> List[CapabilitySnapshot]:
        """Query capabilities with filters."""
        snapshot = self.get_snapshot()
        results = []

        for cap in snapshot.values():
            match = True
            for key, value in filters.items():
                if key == "category" and cap.category != value:
                    match = False
                    break
                elif key == "status" and cap.status.value != value:
                    match = False
                    break
                elif key == "min_confidence" and cap.confidence < value:
                    match = False
                    break
                elif key == "has_evidence_from" and value not in [ev.source for ev in cap.evidence]:
                    match = False
                    break
                elif key == "executable" and not cap.executable_actions:
                    match = False
                    break

            if match:
                results.append(cap)

        return results

    async def execute_capability(self, cap_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a capability if executable actions available."""
        snapshot = self.get_snapshot().get(cap_id)
        if not snapshot or not snapshot.executable_actions:
            return {"error": f"Capability {cap_id} not executable", "status": "not_executable"}

        # For now, route to appropriate worker based on category
        if snapshot.category == "executable_workers":
            # This is a worker itself
            return await self._execute_via_worker(snapshot.id, params)
        else:
            # Find appropriate worker
            worker_snapshots = [s for s in self.get_snapshot().values()
                              if s.category == "executable_workers" and s.status == CapabilityStatus.ACTIVE]
            if not worker_snapshots:
                return {"error": "No active workers available", "status": "no_workers"}

            # Use first available worker (could be smarter routing)
            worker = worker_snapshots[0]
            return await self._execute_via_worker(worker.id, params)

    async def _execute_via_worker(self, worker_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute via specific worker."""
        try:
            if worker_id == "inference_worker":
                from denis_unified_v1.inference import get_inference_router
                router = get_inference_router()
                result = await router.route(params)
                return {"result": result, "status": "success", "worker": "inference_router"}
            elif worker_id == "memory_worker":
                from denis_unified_v1.memory.backends import get_memory_backend
                backend = get_memory_backend()
                if params.get("action") == "store":
                    result = await backend.store(params["key"], params["value"])
                else:
                    result = await backend.retrieve(params["key"])
                return {"result": result, "status": "success", "worker": "memory_backend"}
            # Add other workers...
            else:
                return {"error": f"Worker {worker_id} not implemented", "status": "not_implemented"}
        except Exception as e:
            return {"error": str(e), "status": "execution_failed", "worker": worker_id}


# Global service instance
_capabilities_service = CapabilitiesService()


def get_capabilities_service() -> CapabilitiesService:
    """Get the global capabilities service."""
    return _capabilities_service


def initialize_capabilities_service() -> None:
    """Initialize the capabilities service with default collectors."""
    service = get_capabilities_service()

    # Add collectors
    artifacts_dir = Path(__file__).resolve().parents[2] / "artifacts"
    service.add_collector(ArtifactCollector(artifacts_dir))
    service.add_collector(BackendProbeCollector())
    service.add_collector(GraphCollector())
    service.add_collector(WorkerCollector())

    logger.info("Capabilities service initialized with collectors")


# Initialize on import
initialize_capabilities_service()
