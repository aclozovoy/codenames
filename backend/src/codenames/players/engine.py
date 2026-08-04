"""LLM invocation + cost tracking + a hard budget guard.

`LLMEngine` wraps a client (Bedrock in production, a fake in tests), accumulates
token usage and estimated USD spend across every model it runs, and refuses to
make a call once a configured budget is reached. The model is chosen per call, so
one engine (one shared budget) can drive different models on different seats.
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
    """A model's Bedrock id, display label, price, and sampling settings.

    Prices are USD per million tokens and are approximate — set them from the
    current AWS Bedrock pricing page. They're used only for the local cost guard
    and the usage display, not for billing.
    """

    model_id: str
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    label: str
    max_tokens: int = 1024
    temperature: float = 0.4


# Cheap-first registry — every id below is verified to respond on this account
# via the Converse API. Nova/Llama are dramatically cheaper than Haiku but play
# more loosely; Haiku is the strongest of the cheap set.
MODELS: dict[str, ModelConfig] = {
    "haiku": ModelConfig(
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        input_usd_per_mtok=1.0,
        output_usd_per_mtok=5.0,
        label="Claude Haiku 4.5",
    ),
    "nova-lite": ModelConfig(
        model_id="amazon.nova-lite-v1:0",
        input_usd_per_mtok=0.06,
        output_usd_per_mtok=0.24,
        label="Amazon Nova Lite",
    ),
    "nova-micro": ModelConfig(
        model_id="us.amazon.nova-micro-v1:0",
        input_usd_per_mtok=0.035,
        output_usd_per_mtok=0.14,
        label="Amazon Nova Micro",
    ),
    "llama-8b": ModelConfig(
        model_id="meta.llama3-1-8b-instruct-v1:0",
        input_usd_per_mtok=0.22,
        output_usd_per_mtok=0.22,
        label="Llama 3.1 8B",
    ),
}
DEFAULT_MODEL = "haiku"


class BudgetExceeded(RuntimeError):
    """Raised before a call that would run past the configured USD budget."""


@dataclass
class LLMEngine:
    client: LLMClient
    budget_usd: float | None = None
    total_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    calls: int = 0

    def run(self, system: str, user: str, model: ModelConfig) -> LLMResult:
        """Make one completion with the given model, tracking cost. Hard-stops
        at the shared budget."""
        if self.budget_usd is not None and self.total_usd >= self.budget_usd:
            raise BudgetExceeded(
                f"LLM budget of ${self.budget_usd:.2f} reached "
                f"(spent ${self.total_usd:.4f} over {self.calls} calls)"
            )
        result = self.client.complete(
            model.model_id, system, user, model.max_tokens, model.temperature
        )
        self.calls += 1
        self.total_input_tokens += result.input_tokens
        self.total_output_tokens += result.output_tokens
        self.total_usd += (
            result.input_tokens / 1_000_000 * model.input_usd_per_mtok
            + result.output_tokens / 1_000_000 * model.output_usd_per_mtok
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
