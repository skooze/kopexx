"""Token counting and cross-serialization comparison.

Two responsibilities:

1. Estimate the token cost of a model-visible payload before invocation, so budgets can be
   enforced ahead of spend rather than after it.
2. Measure how many tokens the same information would consume in each serialization, which is
   the evidence base for the plain-text and YAML boundary decision recorded in ADR-0013.

IMPLEMENTATION STATUS: the estimator is a character-ratio heuristic. It is adequate for budget
guards and for relative comparison between serializations of the same content, and it is NOT
adequate for billing reconciliation. A provider-backed exact counter is registered per provider
and used when available. See docs/llm/cost-model.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

# Mean characters per token for English prose with embedded identifiers and numbers. Measured
# ratios for frontier tokenizers cluster between 3.5 and 4.2; 3.8 is a deliberately conservative
# midpoint that slightly over-estimates, which is the safe direction for a budget guard.
CHARS_PER_TOKEN: Final[float] = 3.8


def estimate_tokens(text: str) -> int:
    """Return a conservative token estimate for a string."""
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN + 0.5))


@dataclass(frozen=True)
class SerializationComparison:
    """Token counts for one logical payload across candidate serializations.

    Recorded for every benchmark fixture. ``selected_format`` is always plain_text or yaml
    regardless of which serialization happens to tokenize smallest, because the boundary rule is
    a correctness and security constraint, not an optimization.
    """

    plain_text_tokens: int
    yaml_tokens: int
    markdown_tokens: int
    json_tokens: int
    xml_tokens: int
    selected_format: str
    selected_tokens: int

    def as_record(self) -> dict[str, Any]:
        """Return the comparison in the shape stored alongside benchmark fixtures."""
        return {
            "serialization_comparison": {
                "plain_text_tokens": self.plain_text_tokens,
                "yaml_tokens": self.yaml_tokens,
                "markdown_tokens": self.markdown_tokens,
                "json_tokens": self.json_tokens,
                "xml_tokens": self.xml_tokens,
                "selected_format": self.selected_format,
                "selected_tokens": self.selected_tokens,
            }
        }
