"""
Reality Modeling Engine
========================

Capabilities:
- Causal universe simulation and modeling
- Predictive analytics across all domains
- Reality pattern recognition and analysis
- Multi-scale temporal modeling (micro to cosmic)
- Probabilistic future prediction
- Counterfactual scenario analysis
- Emergent phenomenon detection
- Universal knowledge graph construction

Architecture:
- UniverseSimulator: Simulates causal relationships
- PatternAnalyzer: Recognizes reality patterns
- PredictorEngine: Generates probabilistic predictions
- CounterfactualEngine: Analyzes alternative realities
- KnowledgeIntegrator: Builds universal knowledge graphs
- EmergenceDetector: Identifies emergent phenomena
- TemporalModeler: Handles multi-scale time modeling
"""

from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
import time
import json
import math
import random
from enum import Enum
from collections import defaultdict


class RealityScale(Enum):
    QUANTUM = "quantum"        # 10^-35 to 10^-15 meters
    ATOMIC = "atomic"          # 10^-10 to 10^-9 meters
    MOLECULAR = "molecular"    # 10^-9 to 10^-6 meters
    CELLULAR = "cellular"      # 10^-6 to 10^-3 meters
    ORGANISM = "organism"      # 10^-3 to 10^1 meters
    ECOSYSTEM = "ecosystem"    # 10^1 to 10^6 meters
    PLANETARY = "planetary"    # 10^6 to 10^9 meters
    STELLAR = "stellar"        # 10^9 to 10^16 meters
    GALACTIC = "galactic"      # 10^16 to 10^23 meters
    COSMIC = "cosmic"          # 10^23+ meters


class CausalityType(Enum):
    DETERMINISTIC = "deterministic"
    PROBABILISTIC = "probabilistic"
    QUANTUM = "quantum"
    EMERGENT = "emergent"
    CHAOTIC = "chaotic"


@dataclass
class RealityEntity:
    """An entity in the reality model."""
    id: str
    name: str
    scale: RealityScale
    properties: Dict[str, Any] = field(default_factory=dict)
    relationships: Dict[str, List[str]] = field(default_factory=dict)
    causal_rules: List[Dict[str, Any]] = field(default_factory=list)
    observation_history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class CausalRelationship:
    """A causal relationship between entities."""
    cause_entity: str
    effect_entity: str
    relationship_type: CausalityType
    strength: float
    lag_time: float  # Time delay between cause and effect
    conditions: List[str] = field(default_factory=list)
    confidence: float = 1.0
    observed_instances: int = 0


@dataclass
class RealityPattern:
    """A recognized pattern in reality."""
    id: str
    name: str
    pattern_type: str
    entities_involved: List[str]
    temporal_scope: Tuple[float, float]  # (start_time, end_time)
    spatial_scope: RealityScale
    recurrence_probability: float
    predictive_power: float
    causal_mechanisms: List[str]


@dataclass
class Prediction:
    """A prediction about future reality states."""
    id: str
    target_entity: str
    predicted_property: str
    predicted_value: Any
    confidence: float
    time_horizon: float
    conditions: List[str]
    alternative_scenarios: List[Dict[str, Any]]
    generated_at: float = field(default_factory=time.time)


class UniverseSimulator:
    """Simulates the causal structure of the universe."""

    def __init__(self):
        self.entities: Dict[str, RealityEntity] = {}
        self.relationships: List[CausalRelationship] = []
        self.simulation_history: List[Dict[str, Any]] = []
        self.current_time = time.time()

    def add_entity(self, entity: RealityEntity):
        """Add an entity to the simulation."""
        self.entities[entity.id] = entity

    def add_relationship(self, relationship: CausalRelationship):
        """Add a causal relationship."""
        self.relationships.append(relationship)

    def simulate_time_step(self, time_delta: float) -> Dict[str, Any]:
        """Simulate one time step in the universe."""
        self.current_time += time_delta

        # Apply causal relationships
        changes = {}
        for relationship in self.relationships:
            if relationship.cause_entity in self.entities and relationship.effect_entity in self.entities:
                cause_entity = self.entities[relationship.cause_entity]
                effect_entity = self.entities[relationship.effect_entity]

                # Check if causal conditions are met
                if self._check_causal_conditions(relationship, cause_entity, effect_entity):
                    # Apply causal effect with time lag
                    if random.random() < relationship.strength:
                        effect = self._apply_causal_effect(relationship, cause_entity, effect_entity)
                        if effect:
                            changes[relationship.effect_entity] = effect
                            relationship.observed_instances += 1

        # Record simulation step
        simulation_step = {
            "timestamp": self.current_time,
            "entities_affected": len(changes),
            "changes": changes,
            "active_relationships": len([r for r in self.relationships if r.observed_instances > 0])
        }

        self.simulation_history.append(simulation_step)
        return simulation_step

    def _check_causal_conditions(self, relationship: CausalRelationship,
                                cause_entity: RealityEntity, effect_entity: RealityEntity) -> bool:
        """Check if causal conditions are met."""
        for condition in relationship.conditions:
            # Simple condition checking - in practice this would be more sophisticated
            if ">" in condition:
                parts = condition.split(">")
                if len(parts) == 2:
                    property_name, threshold = parts[0].strip(), float(parts[1].strip())
                    if cause_entity.properties.get(property_name, 0) <= threshold:
                        return False
            elif "<" in condition:
                parts = condition.split("<")
                if len(parts) == 2:
                    property_name, threshold = parts[0].strip(), float(parts[1].strip())
                    if cause_entity.properties.get(property_name, 0) >= threshold:
                        return False

        return True

    def _apply_causal_effect(self, relationship: CausalRelationship,
                           cause_entity: RealityEntity, effect_entity: RealityEntity) -> Optional[Dict[str, Any]]:
        """Apply a causal effect to an entity."""
        # Simple causal effect application - in practice this would be domain-specific
        if relationship.relationship_type == CausalityType.DETERMINISTIC:
            # Direct causal effect
            effect_value = cause_entity.properties.get("value", 0) * relationship.strength
            return {"property": "value", "change": effect_value, "reason": f"caused_by_{cause_entity.id}"}

        elif relationship.relationship_type == CausalityType.PROBABILISTIC:
            # Probabilistic effect
            if random.random() < relationship.strength:
                effect_value = random.gauss(0, 1) * cause_entity.properties.get("value", 1)
                return {"property": "value", "change": effect_value, "reason": f"probabilistic_effect_from_{cause_entity.id}"}

        elif relationship.relationship_type == CausalityType.QUANTUM:
            # Quantum uncertainty effect
            effect_value = cause_entity.properties.get("value", 0) + random.uniform(-1, 1)
            return {"property": "quantum_state", "change": effect_value, "reason": f"quantum_fluctuation_from_{cause_entity.id}"}

        return None

    def run_simulation(self, steps: int, time_delta: float) -> List[Dict[str, Any]]:
        """Run a full simulation for multiple steps."""
        results = []
        for _ in range(steps):
            step_result = self.simulate_time_step(time_delta)
            results.append(step_result)
        return results


class PatternAnalyzer:
    """Analyzes patterns in reality data."""

    def __init__(self):
        self.patterns: Dict[str, RealityPattern] = {}
        self.pattern_templates = self._load_pattern_templates()

    def _load_pattern_templates(self) -> Dict[str, Dict[str, Any]]:
        """Load templates for recognizing different pattern types."""
        return {
            "cyclical": {
                "indicators": ["periodic_behavior", "seasonal_variation", "oscillatory_patterns"],
                "analysis_method": "fourier_transform"
            },
            "emergent": {
                "indicators": ["unexpected_correlations", "novel_properties", "system_level_behavior"],
                "analysis_method": "correlation_networks"
            },
            "chaotic": {
                "indicators": ["sensitive_dependence", "unpredictable_behavior", "strange_attractors"],
                "analysis_method": "lyapunov_exponents"
            },
            "fractal": {
                "indicators": ["self_similarity", "scale_invariance", "complex_structures"],
                "analysis_method": "fractal_dimension"
            }
        }

    def analyze_patterns(self, data_stream: List[Dict[str, Any]]) -> List[RealityPattern]:
        """Analyze a stream of reality data for patterns."""
        patterns_found = []

        # Analyze temporal patterns
        temporal_patterns = self._analyze_temporal_patterns(data_stream)
        patterns_found.extend(temporal_patterns)

        # Analyze spatial patterns
        spatial_patterns = self._analyze_spatial_patterns(data_stream)
        patterns_found.extend(spatial_patterns)

        # Analyze causal patterns
        causal_patterns = self._analyze_causal_patterns(data_stream)
        patterns_found.extend(causal_patterns)

        # Analyze emergent phenomena
        emergent_patterns = self._analyze_emergent_patterns(data_stream)
        patterns_found.extend(emergent_patterns)

        # Store discovered patterns
        for pattern in patterns_found:
            self.patterns[pattern.id] = pattern

        return patterns_found

    def _analyze_temporal_patterns(self, data: List[Dict[str, Any]]) -> List[RealityPattern]:
        """Analyze temporal patterns in data."""
        patterns = []

        # Look for cyclical patterns
        if len(data) > 10:
            # Simple cycle detection
            values = [d.get("value", 0) for d in data if "value" in d]
            if values:
                # Check for periodicity
                autocorr = self._autocorrelation(values)
                if max(autocorr) > 0.7:  # Strong periodicity
                    pattern = RealityPattern(
                        id=f"cycle_{int(time.time())}",
                        name="Cyclical Pattern",
                        pattern_type="cyclical",
                        entities_involved=[d.get("entity_id", "unknown") for d in data],
                        temporal_scope=(data[0].get("timestamp", 0), data[-1].get("timestamp", 0)),
                        spatial_scope=RealityScale.MOLECULAR,  # Default
                        recurrence_probability=max(autocorr),
                        predictive_power=0.8,
                        causal_mechanisms=["periodic_forcing", "feedback_loops"]
                    )
                    patterns.append(pattern)

        return patterns

    def _autocorrelation(self, data: List[float]) -> List[float]:
        """Calculate autocorrelation of a data series."""
        n = len(data)
        mean = sum(data) / n
        variance = sum((x - mean) ** 2 for x in data) / n

        autocorr = []
        for lag in range(1, min(20, n//2)):
            cov = sum((data[i] - mean) * (data[i+lag] - mean) for i in range(n-lag)) / n
            autocorr.append(cov / variance if variance > 0 else 0)

        return autocorr

    def _analyze_spatial_patterns(self, data: List[Dict[str, Any]]) -> List[RealityPattern]:
        """Analyze spatial patterns."""
        # Placeholder for spatial pattern analysis
        return []

    def _analyze_causal_patterns(self, data: List[Dict[str, Any]]) -> List[RealityPattern]:
        """Analyze causal patterns."""
        # Placeholder for causal pattern analysis
        return []

    def _analyze_emergent_patterns(self, data: List[Dict[str, Any]]) -> List[RealityPattern]:
        """Analyze emergent phenomena."""
        patterns = []

        # Look for unexpected correlations
        if len(data) > 5:
            # Simple emergence detection
            properties = set()
            for d in data:
                properties.update(d.keys())

            correlations = {}
            for prop1 in properties:
                for prop2 in properties:
                    if prop1 != prop2:
                        corr = self._calculate_correlation(
                            [d.get(prop1, 0) for d in data if isinstance(d.get(prop1, 0), (int, float))],
                            [d.get(prop2, 0) for d in data if isinstance(d.get(prop2, 0), (int, float))]
                        )
                        if abs(corr) > 0.8:  # Strong correlation
                            correlations[f"{prop1}_{prop2}"] = corr

            if correlations:
                pattern = RealityPattern(
                    id=f"emergence_{int(time.time())}",
                    name="Emergent Correlation Pattern",
                    pattern_type="emergent",
                    entities_involved=list(set(d.get("entity_id", "unknown") for d in data)),
                    temporal_scope=(data[0].get("timestamp", 0), data[-1].get("timestamp", 0)),
                    spatial_scope=RealityScale.ORGANISM,
                    recurrence_probability=0.6,
                    predictive_power=0.7,
                    causal_mechanisms=["emergent_properties", "system_interactions"]
                )
                patterns.append(pattern)

        return patterns

    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi ** 2 for xi in x)
        sum_y2 = sum(yi ** 2 for yi in y)

        numerator = n * sum_xy - sum_x * sum_y
        denominator = math.sqrt((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2))

        return numerator / denominator if denominator != 0 else 0.0


class PredictorEngine:
    """Generates probabilistic predictions about future reality states."""

    def __init__(self):
        self.patterns: Dict[str, RealityPattern] = {}
        self.prediction_history: List[Prediction] = []

    def update_patterns(self, patterns: List[RealityPattern]):
        """Update known patterns for prediction."""
        for pattern in patterns:
            self.patterns[pattern.id] = pattern

    def generate_predictions(self, current_state: Dict[str, Any],
                           time_horizon: float) -> List[Prediction]:
        """Generate predictions about future states."""
        predictions = []

        # Predict based on known patterns
        for pattern in self.patterns.values():
            if pattern.recurrence_probability > 0.5:
                prediction = self._generate_pattern_based_prediction(pattern, current_state, time_horizon)
                if prediction:
                    predictions.append(prediction)

        # Generate baseline predictions
        baseline_predictions = self._generate_baseline_predictions(current_state, time_horizon)
        predictions.extend(baseline_predictions)

        # Store predictions
        self.prediction_history.extend(predictions)

        return predictions

    def _generate_pattern_based_prediction(self, pattern: RealityPattern,
                                         current_state: Dict[str, Any],
                                         time_horizon: float) -> Optional[Prediction]:
        """Generate a prediction based on a known pattern."""
        # Simple pattern-based prediction
        if pattern.pattern_type == "cyclical":
            # Predict next cycle
            predicted_value = self._predict_cyclical_value(pattern, current_state, time_horizon)
            if predicted_value is not None:
                return Prediction(
                    id=f"pred_{pattern.id}_{int(time.time())}",
                    target_entity=pattern.entities_involved[0],
                    predicted_property="value",
                    predicted_value=predicted_value,
                    confidence=pattern.recurrence_probability * 0.8,
                    time_horizon=time_horizon,
                    conditions=[f"pattern_{pattern.id}_continues"],
                    alternative_scenarios=[
                        {"scenario": "pattern_breaks", "probability": 1-pattern.recurrence_probability, "value": None},
                        {"scenario": "pattern_amplifies", "probability": 0.2, "value": predicted_value * 1.5}
                    ]
                )

        return None

    def _predict_cyclical_value(self, pattern: RealityPattern,
                              current_state: Dict[str, Any],
                              time_horizon: float) -> Optional[float]:
        """Predict value for cyclical pattern."""
        # Simple sinusoidal prediction
        current_time = time.time()
        cycle_period = (pattern.temporal_scope[1] - pattern.temporal_scope[0]) / 2  # Assume 2 cycles

        if cycle_period > 0:
            phase = (current_time % cycle_period) / cycle_period
            predicted_phase = ((current_time + time_horizon) % cycle_period) / cycle_period

            # Simple prediction: continue the pattern
            return math.sin(predicted_phase * 2 * math.pi)

        return None

    def _generate_baseline_predictions(self, current_state: Dict[str, Any],
                                     time_horizon: float) -> List[Prediction]:
        """Generate baseline predictions without specific patterns."""
        predictions = []

        # Predict continuation of current trends
        for entity_id, entity_data in current_state.items():
            if isinstance(entity_data, dict) and "value" in entity_data:
                current_value = entity_data["value"]
                # Simple linear trend continuation
                predicted_value = current_value * (1 + random.uniform(-0.1, 0.1))

                prediction = Prediction(
                    id=f"baseline_{entity_id}_{int(time.time())}",
                    target_entity=entity_id,
                    predicted_property="value",
                    predicted_value=predicted_value,
                    confidence=0.6,  # Lower confidence for baseline predictions
                    time_horizon=time_horizon,
                    conditions=["no_major_disruptions"],
                    alternative_scenarios=[
                        {"scenario": "upward_trend", "probability": 0.3, "value": current_value * 1.2},
                        {"scenario": "downward_trend", "probability": 0.3, "value": current_value * 0.8},
                        {"scenario": "stable", "probability": 0.4, "value": current_value}
                    ]
                )
                predictions.append(prediction)

        return predictions

    def evaluate_predictions(self, actual_outcomes: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate prediction accuracy."""
        correct_predictions = 0
        total_predictions = 0

        evaluation_results = {
            "total_predictions": len(self.prediction_history),
            "predictions_within_horizon": 0,
            "accuracy_by_confidence": {},
            "accuracy_by_time_horizon": {}
        }

        current_time = time.time()

        for prediction in self.prediction_history:
            # Only evaluate predictions that are past their horizon
            if current_time >= prediction.generated_at + prediction.time_horizon:
                total_predictions += 1
                evaluation_results["predictions_within_horizon"] += 1

                # Check if prediction was accurate
                actual_value = actual_outcomes.get(prediction.target_entity, {}).get(prediction.predicted_property)
                if actual_value is not None:
                    accuracy = self._calculate_prediction_accuracy(prediction.predicted_value, actual_value)
                    if accuracy > 0.8:  # Consider accurate if within 20%
                        correct_predictions += 1

                    # Track accuracy by confidence
                    confidence_bucket = int(prediction.confidence * 10) / 10  # Round to nearest 0.1
                    if confidence_bucket not in evaluation_results["accuracy_by_confidence"]:
                        evaluation_results["accuracy_by_confidence"][confidence_bucket] = {"correct": 0, "total": 0}
                    evaluation_results["accuracy_by_confidence"][confidence_bucket]["total"] += 1
                    if accuracy > 0.8:
                        evaluation_results["accuracy_by_confidence"][confidence_bucket]["correct"] += 1

        evaluation_results["overall_accuracy"] = correct_predictions / max(1, total_predictions)
        evaluation_results["correct_predictions"] = correct_predictions

        return evaluation_results

    def _calculate_prediction_accuracy(self, predicted: Any, actual: Any) -> float:
        """Calculate prediction accuracy."""
        if isinstance(predicted, (int, float)) and isinstance(actual, (int, float)):
            if actual == 0:
                return 1.0 if predicted == 0 else 0.0
            return 1.0 - abs(predicted - actual) / abs(actual)
        elif predicted == actual:
            return 1.0
        else:
            return 0.0


class CounterfactualEngine:
    """Analyzes alternative reality scenarios."""

    def __init__(self):
        self.scenarios: Dict[str, Dict[str, Any]] = {}

    def generate_counterfactuals(self, base_state: Dict[str, Any],
                               variables_to_change: List[str]) -> List[Dict[str, Any]]:
        """Generate counterfactual scenarios by changing key variables."""
        counterfactuals = []

        for variable in variables_to_change:
            if variable in base_state:
                # Generate scenarios with different values for this variable
                current_value = base_state[variable]

                # Generate multiple counterfactuals
                scenarios = [
                    {**base_state, variable: current_value * 0.5, "scenario_type": f"{variable}_reduced"},
                    {**base_state, variable: current_value * 1.5, "scenario_type": f"{variable}_increased"},
                    {**base_state, variable: 0, "scenario_type": f"{variable}_zero"},
                    {**base_state, variable: current_value * -1, "scenario_type": f"{variable}_negative"}
                ]

                counterfactuals.extend(scenarios)

        return counterfactuals

    def simulate_counterfactual(self, counterfactual_state: Dict[str, Any],
                              simulation_steps: int) -> Dict[str, Any]:
        """Simulate the evolution of a counterfactual scenario."""
        # Create a temporary simulator for this counterfactual
        simulator = UniverseSimulator()

        # Add entities based on counterfactual state
        for entity_id, entity_data in counterfactual_state.items():
            if isinstance(entity_data, dict) and "properties" in entity_data:
                entity = RealityEntity(
                    id=entity_id,
                    name=entity_data.get("name", entity_id),
                    scale=RealityScale.ORGANISM,  # Default
                    properties=entity_data["properties"]
                )
                simulator.add_entity(entity)

        # Run simulation
        simulation_results = simulator.run_simulation(simulation_steps, 1.0)

        return {
            "counterfactual_state": counterfactual_state,
            "simulation_results": simulation_results,
            "final_state": simulator.entities,
            "key_events": [step for step in simulation_results if step["entities_affected"] > 0]
        }


class RealityModelingEngine:
    """The main reality modeling engine that orchestrates all components."""

    def __init__(self):
        self.simulator = UniverseSimulator()
        self.pattern_analyzer = PatternAnalyzer()
        self.predictor = PredictorEngine()
        self.counterfactual_engine = CounterfactualEngine()

        self.knowledge_graph: Dict[str, Any] = {}
        self.model_history: List[Dict[str, Any]] = []

    async def model_reality(self, observation_data: List[Dict[str, Any]],
                          prediction_horizon: float = 3600) -> Dict[str, Any]:
        """Build and update the reality model."""
        start_time = time.time()

        # 1. Analyze patterns in observation data
        patterns = self.pattern_analyzer.analyze_patterns(observation_data)

        # 2. Update predictor with new patterns
        self.predictor.update_patterns(patterns)

        # 3. Generate predictions
        current_state = self._extract_current_state(observation_data)
        predictions = self.predictor.generate_predictions(current_state, prediction_horizon)

        # 4. Generate counterfactual scenarios
        key_variables = self._identify_key_variables(observation_data)
        counterfactuals = self.counterfactual_engine.generate_counterfactuals(current_state, key_variables)

        # 5. Run counterfactual simulations
        counterfactual_simulations = []
        for counterfactual in counterfactuals[:5]:  # Limit to 5 for performance
            simulation = self.counterfactual_engine.simulate_counterfactual(counterfactual, 10)
            counterfactual_simulations.append(simulation)

        # 6. Update knowledge graph
        self._update_knowledge_graph(observation_data, patterns, predictions)

        total_time = time.time() - start_time

        result = {
            "modeling_time": total_time,
            "patterns_discovered": len(patterns),
            "predictions_generated": len(predictions),
            "counterfactuals_analyzed": len(counterfactual_simulations),
            "current_state": current_state,
            "key_patterns": [p.__dict__ for p in patterns[:3]],  # Top 3 patterns
            "top_predictions": [p.__dict__ for p in predictions[:5]],  # Top 5 predictions
            "counterfactual_insights": self._extract_counterfactual_insights(counterfactual_simulations),
            "model_accuracy": self._assess_model_accuracy(),
            "knowledge_graph_nodes": len(self.knowledge_graph)
        }

        # Store modeling session
        self.model_history.append({
            "timestamp": time.time(),
            "result": result,
            "observation_count": len(observation_data)
        })

        return result

    def _extract_current_state(self, observation_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract current state from observation data."""
        current_state = {}

        if observation_data:
            latest_observation = max(observation_data, key=lambda x: x.get("timestamp", 0))

            # Extract entity states
            for key, value in latest_observation.items():
                if key not in ["timestamp", "source"] and isinstance(value, (int, float, str, bool)):
                    current_state[key] = value

        return current_state

    def _identify_key_variables(self, observation_data: List[Dict[str, Any]]) -> List[str]:
        """Identify key variables that drive system behavior."""
        variables = set()

        for observation in observation_data:
            for key, value in observation.items():
                if isinstance(value, (int, float)) and key not in ["timestamp", "source"]:
                    variables.add(key)

        # Return variables that appear in most observations
        variable_counts = {}
        for observation in observation_data:
            for var in variables:
                if var in observation:
                    variable_counts[var] = variable_counts.get(var, 0) + 1

        # Return top variables
        sorted_vars = sorted(variable_counts.items(), key=lambda x: x[1], reverse=True)
        return [var for var, count in sorted_vars[:5]]  # Top 5 variables

    def _update_knowledge_graph(self, observations: List[Dict[str, Any]],
                              patterns: List[RealityPattern],
                              predictions: List[Prediction]):
        """Update the universal knowledge graph."""
        # Add observation nodes
        for observation in observations:
            obs_id = f"obs_{observation.get('timestamp', time.time())}"
            self.knowledge_graph[obs_id] = {
                "type": "observation",
                "data": observation,
                "connected_patterns": [],
                "connected_predictions": []
            }

        # Add pattern nodes and connections
        for pattern in patterns:
            pattern_id = f"pattern_{pattern.id}"
            self.knowledge_graph[pattern_id] = {
                "type": "pattern",
                "data": pattern.__dict__,
                "connected_observations": [],
                "predictive_power": pattern.predictive_power
            }

            # Connect pattern to relevant observations
            for obs_id, obs_data in self.knowledge_graph.items():
                if obs_data["type"] == "observation":
                    # Simple relevance check
                    if any(entity in str(obs_data["data"]) for entity in pattern.entities_involved):
                        self.knowledge_graph[pattern_id]["connected_observations"].append(obs_id)
                        self.knowledge_graph[obs_id]["connected_patterns"].append(pattern_id)

        # Add prediction nodes
        for prediction in predictions:
            pred_id = f"pred_{prediction.id}"
            self.knowledge_graph[pred_id] = {
                "type": "prediction",
                "data": prediction.__dict__,
                "confidence": prediction.confidence,
                "fulfilled": False
            }

    def _extract_counterfactual_insights(self, simulations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract insights from counterfactual simulations."""
        insights = []

        for simulation in simulations:
            final_state = simulation.get("final_state", {})
            key_events = simulation.get("key_events", [])

            insight = {
                "scenario": simulation["counterfactual_state"].get("scenario_type", "unknown"),
                "final_entities_affected": len(final_state),
                "key_events_count": len(key_events),
                "simulation_steps": len(simulation.get("simulation_results", [])),
                "significance": "high" if len(key_events) > 5 else "medium" if len(key_events) > 2 else "low"
            }

            insights.append(insight)

        return insights

    def _assess_model_accuracy(self) -> float:
        """Assess overall model accuracy."""
        if not self.model_history:
            return 0.5  # Default accuracy

        recent_models = self.model_history[-10:]  # Last 10 modeling sessions
        total_accuracy = sum(model["result"].get("model_accuracy", 0.5) for model in recent_models)

        return total_accuracy / len(recent_models)

    def query_knowledge_graph(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query the knowledge graph for insights."""
        results = []

        query_type = query.get("type")
        entity_filter = query.get("entity")
        pattern_filter = query.get("pattern")

        for node_id, node_data in self.knowledge_graph.items():
            if query_type and node_data.get("type") != query_type:
                continue

            if entity_filter and entity_filter not in node_id:
                continue

            if pattern_filter and pattern_filter not in str(node_data):
                continue

            results.append({
                "id": node_id,
                "type": node_data["type"],
                "data": node_data["data"],
                "connections": {
                    "patterns": node_data.get("connected_patterns", []),
                    "observations": node_data.get("connected_observations", []),
                    "predictions": node_data.get("connected_predictions", [])
                }
            })

        return results[:50]  # Limit results

    def get_model_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the reality model."""
        node_types = defaultdict(int)
        connection_count = 0

        for node_data in self.knowledge_graph.values():
            node_types[node_data["type"]] += 1
            connection_count += len(node_data.get("connected_patterns", []))
            connection_count += len(node_data.get("connected_observations", []))
            connection_count += len(node_data.get("connected_predictions", []))

        return {
            "total_nodes": len(self.knowledge_graph),
            "node_types": dict(node_types),
            "total_connections": connection_count,
            "modeling_sessions": len(self.model_history),
            "patterns_discovered": len(self.pattern_analyzer.patterns),
            "predictions_made": len(self.predictor.prediction_history),
            "average_model_accuracy": self._assess_model_accuracy(),
            "knowledge_graph_density": connection_count / max(1, len(self.knowledge_graph))
        }


# Global instance
_reality_engine = RealityModelingEngine()


async def model_reality(observation_data: List[Dict[str, Any]],
                       prediction_horizon: float = 3600) -> Dict[str, Any]:
    """Model reality using all available data."""
    return await _reality_engine.model_reality(observation_data, prediction_horizon)


def query_reality_model(query: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Query the reality model for insights."""
    return _reality_engine.query_knowledge_graph(query)


def get_reality_model_stats() -> Dict[str, Any]:
    """Get comprehensive reality model statistics."""
    return _reality_engine.get_model_statistics()
