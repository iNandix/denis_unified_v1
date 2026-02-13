"""Anomaly detection basado en L1PatternDetector."""
import time
from typing import List, Dict
import redis
import os

class AnomalyDetector:
    """Detecta anomalías en métricas del sistema."""
    
    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self.thresholds = {
            "ttft_ms": 1000,
            "latency_ms": 2000,
            "success_rate": 0.85,
            "error_rate": 0.1,
        }
    
    def detect(self) -> List[Dict]:
        """Detecta anomalías en métricas recientes."""
        anomalies = []
        
        # 1) TTFT anomalía
        ttft_values = self.redis.lrange("metrics:ttft", 0, 99)
        if ttft_values:
            ttft_ints = [int(x) for x in ttft_values]
            avg_ttft = sum(ttft_ints) // len(ttft_ints)
            p95_ttft = sorted(ttft_ints)[int(len(ttft_ints) * 0.95)]
            
            if avg_ttft > self.thresholds["ttft_ms"]:
                anomalies.append({
                    "type": "high_ttft",
                    "metric": "ttft_ms",
                    "value": avg_ttft,
                    "threshold": self.thresholds["ttft_ms"],
                    "severity": "high",
                    "message": f"TTFT promedio {avg_ttft}ms excede threshold {self.thresholds['ttft_ms']}ms",
                })
            
            if p95_ttft > self.thresholds["ttft_ms"] * 1.5:
                anomalies.append({
                    "type": "high_ttft_p95",
                    "metric": "ttft_p95",
                    "value": p95_ttft,
                    "threshold": self.thresholds["ttft_ms"] * 1.5,
                    "severity": "critical",
                    "message": f"TTFT p95 {p95_ttft}ms crítico",
                })
        
        # 2) Error rate anomalía
        error_count = int(self.redis.get("errors:count") or 0)
        success_count = int(self.redis.get("success:count") or 1)
        total = error_count + success_count
        error_rate = error_count / total if total > 0 else 0
        
        if error_rate > self.thresholds["error_rate"]:
            anomalies.append({
                "type": "high_error_rate",
                "metric": "error_rate",
                "value": error_rate,
                "threshold": self.thresholds["error_rate"],
                "severity": "critical",
                "message": f"Error rate {error_rate:.2%} excede threshold {self.thresholds['error_rate']:.2%}",
            })
        
        # 3) Usar L1PatternDetector para patterns emergentes
        from denis_unified_v1.metagraph.active_metagraph import L1PatternDetector
        detector = L1PatternDetector()
        patterns = detector.detect_patterns()
        
        for pattern in patterns:
            if pattern["severity"] in ["high", "critical"]:
                anomalies.append({
                    "type": "pattern_detected",
                    "metric": pattern["type"],
                    "value": pattern["metric"],
                    "severity": pattern["severity"],
                    "message": pattern["proposal"],
                })
        
        return anomalies


class AlertManager:
    """Gestiona alertas y notificaciones."""
    
    def __init__(self):
        self.detector = AnomalyDetector()
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    
    async def check_and_alert(self):
        """Chequea anomalías y envía alertas."""
        anomalies = self.detector.detect()
        
        if not anomalies:
            return {"status": "ok", "anomalies": 0}
        
        # Enviar alertas
        for anomaly in anomalies:
            if anomaly["severity"] in ["high", "critical"]:
                await self._send_alert(anomaly)
        
        return {"status": "anomalies_detected", "anomalies": len(anomalies), "details": anomalies}
    
    async def _send_alert(self, anomaly: Dict):
        """Envía alerta a Slack."""
        if not self.slack_webhook:
            return
        
        import httpx
        
        message = f"🚨 **{anomaly['severity'].upper()}**: {anomaly['message']}"
        
        async with httpx.AsyncClient() as client:
            try:
                await client.post(self.slack_webhook, json={"text": message})
            except:
                pass  # No bloquear si Slack falla
