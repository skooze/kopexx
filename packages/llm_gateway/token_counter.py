"""Token estimation for model-visible payloads.

Estimates the token cost of a payload before invocation, so budgets can be enforced ahead of spend
rather than reconciled after it.

IMPLEMENTATION STATUS: a character-ratio heuristic. It is adequate for budget guards and for
relative comparison between serializations of the same content, and it is NOT adequate for billing
reconciliation. Every token figure this project has ever published is an estimate from this ratio,
never a provider tokenizer count. A provider-backed exact counter is registered per provider and
used when one exists; none does, because no provider has been reached. See docs/llm/cost-model.md.

`SerializationComparison` was removed with this rewrite. It was the evidence shape for the
plain-text-versus-YAML boundary decision in ADR-0013, that decision is made and recorded, and the
dataclass had no constructor and no test anywhere in the repository.
"""

from __future__ import annotations

from typing import Final

# Mean characters per token for English prose with embedded identifiers and numbers. Measured
# ratios for frontier tokenizers cluster between 3.5 and 4.2; 3.8 is a deliberately conservative
# midpoint that slightly over-estimates, which is the safe direction for a budget guard.
CHARS_PER_TOKEN: Final[float] = 3.8


def estimate_tokens(text: str) -> int:
    """Return a conservative token estimate for a string."""
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN + 0.5))
