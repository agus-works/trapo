from __future__ import annotations

from trapo.token_estimator import estimate_ontology_tokens, estimate_text_tokens

MIN_STRUCTURED_OUTPUT_TOKENS = 2048


def test_estimate_text_tokens_uses_nonzero_heuristic() -> None:
    assert estimate_text_tokens("hello world") > 0


def test_ontology_estimate_has_structured_output_budget() -> None:
    estimate = estimate_ontology_tokens("hello world", "extract facts")

    assert estimate.prompt_tokens > estimate.text_tokens
    assert estimate.recommended_output_tokens >= MIN_STRUCTURED_OUTPUT_TOKENS
