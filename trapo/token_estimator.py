from __future__ import annotations

from dataclasses import dataclass
from math import ceil


STRUCTURED_OUTPUT_OVERHEAD_TOKENS = 900


@dataclass(frozen=True)
class TokenEstimate:
    text_tokens: int
    prompt_tokens: int
    recommended_output_tokens: int


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    char_estimate = ceil(len(text) / 4)
    word_estimate = ceil(len(text.split()) * 1.35)
    return max(1, char_estimate, word_estimate)


def estimate_ontology_tokens(chunk_text: str, system_prompt: str) -> TokenEstimate:
    text_tokens = estimate_text_tokens(chunk_text)
    prompt_tokens = (
        text_tokens
        + estimate_text_tokens(system_prompt)
        + STRUCTURED_OUTPUT_OVERHEAD_TOKENS
    )
    recommended_output_tokens = max(2048, min(8192, ceil(text_tokens * 1.25)))
    return TokenEstimate(
        text_tokens=text_tokens,
        prompt_tokens=prompt_tokens,
        recommended_output_tokens=recommended_output_tokens,
    )
