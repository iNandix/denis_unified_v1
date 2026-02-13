"""
Metacognitive Perception (Fase 1).
El cortex reflexiona sobre su propia percepción.
"""
import time
from typing import Dict, List


class PerceptionReflection:
    """Reflexiona sobre percepciones del cortex."""
    
    def reflect(self, perception: Dict) -> Dict:
        """
        Genera metadata metacognitiva sobre una percepción.
        
        Returns:
            - confidence: ¿Qué tan confiable es esta percepción?
            - importance: ¿Qué tan importante es?
            - gaps: ¿Qué entidades faltan?
            - attention_score: ¿Merece atención?
        """
        entities = perception.get("entities", [])
        
        # Confidence: basado en freshness de datos
        freshness_scores = [
            self._calculate_freshness(e.get("last_updated", 0))
            for e in entities
        ]
        confidence = sum(freshness_scores) / len(freshness_scores) if freshness_scores else 0.5
        
        # Importance: basado en tipo de entidad
        importance = self._calculate_importance(entities)
        
        # Gaps: detectar entidades esperadas pero ausentes
        gaps = self._detect_gaps(entities)
        
        # Attention score: combinación de confidence e importance
        attention_score = (confidence * 0.5) + (importance * 0.5)
        
        return {
            "confidence": confidence,
            "importance": importance,
            "gaps": gaps,
            "attention_score": attention_score,
            "timestamp": time.time(),
        }
    
    def _calculate_freshness(self, last_updated: float) -> float:
        """Freshness decay: datos antiguos tienen menor confidence."""
        age_seconds = time.time() - last_updated
        if age_seconds < 60:
            return 1.0
        elif age_seconds < 300:
            return 0.8
        elif age_seconds < 3600:
            return 0.5
        else:
            return 0.2
    
    def _calculate_importance(self, entities: List[Dict]) -> float:
        """Importance basado en tipo de entidad."""
        important_types = {"user", "system", "critical_service"}
        important_count = sum(1 for e in entities if e.get("type") in important_types)
        return min(1.0, important_count / max(1, len(entities)))
    
    def _detect_gaps(self, entities: List[Dict]) -> List[str]:
        """Detecta entidades esperadas pero ausentes."""
        expected = {"denis_persona", "neo4j", "redis", "smx_motors"}
        present = {e.get("name") for e in entities}
        return list(expected - present)


class AttentionMechanism:
    """Decide qué entidades merecen atención."""
    
    def prioritize(self, entities: List[Dict], reflection: Dict) -> List[Dict]:
        """
        Ordena entidades por prioridad de atención.
        """
        scored = []
        for entity in entities:
            score = 0.0
            
            # Estado crítico → alta prioridad
            if entity.get("status") == "error":
                score += 1.0
            elif entity.get("status") == "degraded":
                score += 0.5
            
            # Gaps detectados → alta prioridad
            if entity.get("name") in reflection.get("gaps", []):
                score += 0.8
            
            # Importancia base
            score += reflection.get("importance", 0.0) * 0.3
            
            scored.append({"entity": entity, "priority": score})
        
        # Ordenar por prioridad descendente
        scored.sort(key=lambda x: x["priority"], reverse=True)
        
        return [s["entity"] for s in scored]