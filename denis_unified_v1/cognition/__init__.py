"""DENIS Cognition Module.

Provides:
- Executor: Evidence-based tool execution
- Evaluator: Result evaluation against acceptance criteria
- ReentryController: Manages iteration (max 2 re-entries)
"""

from denis_unified_v1.cognition.executor import (
    Executor,
    Evaluator,
    ReentryController,
    PlanExecutionResult,
    StepExecutionResult,
    EvaluationResult,
    ReentryDecision,
    save_toolchain_log,
)

from denis_unified_v1.cognition.response_composer import (
    PersonaResponseComposer,
    PersonaResponse,
    save_composer_snapshot,
)

__all__ = [
    "Executor",
    "Evaluator",
    "ReentryController",
    "PlanExecutionResult",
    "StepExecutionResult",
    "EvaluationResult",
    "ReentryDecision",
    "PersonaResponseComposer",
    "PersonaResponse",
    "save_toolchain_log",
    "save_composer_snapshot",
]
