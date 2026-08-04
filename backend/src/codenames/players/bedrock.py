"""Bedrock client (boto3 Converse API). The only module that imports boto3."""

from __future__ import annotations

import boto3

from .engine import LLMResult


class BedrockClient:
    """Calls Bedrock's Converse API. Newer Claude models require an inference
    profile id (e.g. ``us.anthropic.claude-haiku-4-5-...``), which is what the
    MODELS registry stores."""

    def __init__(self, region: str = "us-west-2") -> None:
        self._runtime = boto3.client("bedrock-runtime", region_name=region)

    def complete(
        self, model_id: str, system: str, user: str, max_tokens: int, temperature: float
    ) -> LLMResult:
        resp = self._runtime.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        blocks = resp["output"]["message"]["content"]
        text = "".join(b.get("text", "") for b in blocks)
        usage = resp["usage"]
        return LLMResult(
            text=text,
            input_tokens=usage["inputTokens"],
            output_tokens=usage["outputTokens"],
        )
