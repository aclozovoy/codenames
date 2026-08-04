"""LLM players (AWS Bedrock): spymaster + operative, with visible reasoning.

The engine and API stay pure; this package is the only place that talks to
Bedrock. Players return structured decisions that always include the model's
`reasoning`, so the UI can show what the model was thinking.
"""

from .engine import DEFAULT_MODEL, MODELS, BudgetExceeded, LLMEngine, LLMResult, ModelConfig
from .operative import GuessDecision, LLMOperative
from .spymaster import ClueDecision, LLMSpymaster

__all__ = [
    "DEFAULT_MODEL",
    "MODELS",
    "BudgetExceeded",
    "ClueDecision",
    "GuessDecision",
    "LLMEngine",
    "LLMOperative",
    "LLMResult",
    "LLMSpymaster",
    "ModelConfig",
]
