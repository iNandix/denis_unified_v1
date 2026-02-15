# P2 - Intent System Refinements (Future Work)

> Based on analysis of low-confidence edge cases and production requirements.

## Current State (P1 Complete ✅)

- Binary confidence threshold: ≥0.72
- Two outcomes: proceed OR ask clarification/offer options
- Heuristics-based classification with LLM fallback
- 91.3% accuracy on eval dataset

## Proposed P2 Improvements

### 1. Confidence Bands (Not Binary)

Replace single threshold with three bands:

```python
class ConfidenceBand(Enum):
    HIGH = "high"      # >= 0.85 - Full tool execution
    MEDIUM = "medium"  # 0.72-0.85 - Read-only tools only
    LOW = "low"        # < 0.72 - Question or plans

# Rules:
# HIGH: Can execute any tool including mutations
# MEDIUM: Only read/list/probe actions (safe)
# LOW: Must clarify before any action
```

**Benefits:**
- Reduces false negatives
- Allows partial automation for ambiguous cases
- Better UX for "medium clear" intents

### 2. Low Confidence Mode - Actionable Output

Current: Block with question

Proposed: Always return actionable structure:

```json
{
  "mode": "low_confidence",
  "question": "¿Quieres que lo arregle (código) o solo explique el error?",
  "plans": [
    {"id": "A", "summary": "Diagnosticar y proponer fix"},
    {"id": "B", "summary": "Explicar causa y pasos manuales"}
  ],
  "safe_next_step": {
    "type": "read_only",
    "command": "pytest -q --tb=short"
  }
}
```

**Rules:**
1. Always have `question` OR `plans`
2. If technical intent suspected, include `safe_next_step` (read-only)
3. Never return empty "I don't understand"

### 3. Separate Risk Score

Add risk assessment independent of confidence:

```python
@dataclass
class IntentAssessment:
    intent: IntentType
    confidence: float  # 0-1
    risk: RiskLevel    # LOW / MEDIUM / HIGH
    
    @property
    def can_execute(self) -> bool:
        if self.risk == RiskLevel.HIGH:
            return False  # Always ask, even with high confidence
        return self.confidence >= 0.72
    
    @property
    def can_read_only(self) -> bool:
        if self.risk == RiskLevel.HIGH:
            return self.confidence >= 0.85
        return self.confidence >= 0.50
```

**Risk indicators:**
- Production environment mentioned
- Data mutation keywords
- Security-related terms
- Multiple systems affected

### 4. Disambiguation Templates

When stuck between 2-3 intents, ask targeted question:

```python
DISAMBIGUATION_TEMPLATES = {
    (IntentType.DEBUG_REPO, IntentType.RUN_TESTS_CI): {
        "question": "¿El error ocurre en tu máquina local o solo en CI?",
        "clarification_map": {
            "local": IntentType.DEBUG_REPO,
            "ci": IntentType.RUN_TESTS_CI,
        }
    },
    (IntentType.IMPLEMENT_FEATURE, IntentType.REFACTOR_MIGRATION): {
        "question": "¿Quieres añadir comportamiento nuevo o reestructurar sin cambiar output?",
        "clarification_map": {
            "nuevo": IntentType.IMPLEMENT_FEATURE,
            "reestructurar": IntentType.REFACTOR_MIGRATION,
        }
    },
    (IntentType.OPS_HEALTH_CHECK, IntentType.INCIDENT_TRIAGE): {
        "question": "¿Buscas el estado actual o investigar un fallo activo?",
        "clarification_map": {
            "estado": IntentType.OPS_HEALTH_CHECK,
            "fallo": IntentType.INCIDENT_TRIAGE,
        }
    },
}
```

**Benefits:**
- Higher "1 question" resolution rate
- Faster than offering 2 full plans
- User learns intent taxonomy

### 5. Unknown Intent Fallback Plan

When truly unknown, provide universal diagnostic:

```json
{
  "mode": "unknown_intent",
  "message": "No estoy seguro de qué necesitas. Voy a recopilar información...",
  "universal_plan": {
    "steps": [
      {"action": "collect_context", "what": "error logs, commands, paths mentioned"},
      {"action": "identify_goal", "what": "fix, explain, implement, or check"},
      {"action": "propose_next", "what": "specific next step based on findings"}
    ],
    "safe_actions": [
      "list files in mentioned paths",
      "check recent git changes",
      "run tests in dry-mode",
      "read relevant documentation"
    ]
  }
}
```

### 6. Confidence Calibration Improvements

Current issues:
- Single match gives 0.75 (may be too high)
- No penalty for conflicting signals

Proposed scoring:

```python
def calculate_confidence(matches: int, signals: Dict) -> float:
    base = 0.65 if matches == 1 else 0.80 if matches == 2 else 0.90
    
    # Penalties
    if signals.get("intent_conflict"):
        base -= 0.15
    if signals.get("irony_detected"):
        base -= 0.20
    if signals.get("very_short_prompt"):
        base -= 0.10
        
    # Bonuses
    if signals.get("entity_extracted"):
        base += 0.05
    if signals.get("clear_action_verb"):
        base += 0.05
        
    return min(max(base, 0.0), 0.95)
```

## Implementation Priority

### Phase 1 (Quick Wins)
1. ✅ Confidence bands (HIGH/MEDIUM/LOW)
2. ✅ Actionable low-confidence output
3. ✅ Basic risk assessment

### Phase 2 (Medium Effort)
4. Disambiguation templates
5. Unknown intent fallback plan

### Phase 3 (Advanced)
6. Confidence calibration with penalties
7. Irony/ambiguity detection
8. Meta-intent LLM integration

## Test Requirements

New tests needed:

```python
def test_confidence_bands():
    """Verify HIGH/MEDIUM/LOW bands work correctly."""
    pass

def test_low_confidence_has_actionable_output():
    """Verify low confidence always returns question or plans."""
    pass

def test_medium_confidence_only_read_only():
    """Verify MEDIUM band only allows read-only tools."""
    pass

def test_high_risk_blocks_execution():
    """Verify HIGH risk prevents execution even with high confidence."""
    pass

def test_disambiguation_templates():
    """Verify common intent pairs have disambiguation questions."""
    pass
```

## Acceptance Criteria for P2

- [ ] Confidence bands implemented with proper gating
- [ ] Low confidence always returns actionable output
- [ ] Risk assessment blocks dangerous actions
- [ ] Disambiguation templates cover top 5 intent pairs
- [ ] Unknown intent provides universal diagnostic plan
- [ ] All new functionality has tests
- [ ] Documentation updated with examples

## Notes

These improvements address real edge cases seen in P1:
- "No funciona" matched debug_repo (correct but unexpected)
- Ambiguous prompts between debug vs test
- Vague requests that could be feature or refactor

The goal is to make the system:
1. **More helpful** - Never block without options
2. **Safer** - Risk-aware execution
3. **Faster** - Better disambiguation
4. **Calibrated** - Honest confidence scores
