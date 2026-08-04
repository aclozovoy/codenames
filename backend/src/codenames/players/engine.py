"""LLM invocation + cost tracking + a hard budget guard.

`LLMEngine` wraps a client (Bedrock in production, a fake in tests), accumulates
token usage and estimated USD spend, and refuses to make a call once a configured
budget is reached. This is the cost guard we control directly — independent of any
AWS-account budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResult:
    """One model completion plus its token usage."""

    text: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    """Anything that can turn a system+user prompt into an LLMResult."""

    def complete(
        self, model_id: str, system: str, user: str, max_tokens: int, temperature: float
    ) -> LLMResult: ...


@dataclass(frozen=True)
class ModelConfig:
    """A model's Bedrock id, price, and sampling settings.

    Prices are USD per million tokens and are approximate — set them from the
    current AWS Bedrock pricing page. They're used only for the local cost guard
    and the usage display, not for billing.
    """

    model_id: str
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    max_tokens: int = 512
    temperature: float = 0.4


# Cheap-first registry. Haiku is validated against this account; add more as needed.
MODELS: dict[str, ModelConfig] = {
    "haiku": ModelConfig(
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        input_usd_per_mtok=1.0,
        output_usd_per_mtok=5.0,
    ),
}
DEFAULT_MODEL = "haiku"


class BudgetExceeded(RuntimeError):
    """Raised before a call that would run past the configured USD budget."""


@dataclass
class LLMEngine:
    client: LLMClient
    model: ModelConfig
    budget_usd: float | None = None
    total_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    calls: int = 0

    def run(self, system: str, user: str) -> LLMResult:
        """Make one completion, tracking cost. Hard-stops at the budget."""
        if self.budget_usd is not None and self.total_usd >= self.budget_usd:
            raise BudgetExceeded(
                f"LLM budget of ${self.budget_usd:.2f} reached "
                f"(spent ${self.total_usd:.4f} over {self.calls} calls)"
            )
        result = self.client.complete(
            self.model.model_id, system, user, self.model.max_tokens, self.model.temperature
        )
        self.calls += 1
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens
        self.total_usd += (
            result.input_tokens / 1_000_000 * self.model.input_usd_per_mtok
            + result.output_tokens / 1_000_000 * self.model.output_usd_per_mtok
        )
        return result

    @property
    def usage(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "usd": round(self.total_usd, 6),
            "budget_usd": self.budget_usd,
        }
