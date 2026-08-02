"""Stage 2 — filing-item exclusion, driven by a maintained definition file.

The SEC renderer files certain Regulation S-K item disclosures under menu category `Notes`. They
are not financial-statement footnotes. Apple's FY2025 10-K has three: two Item 408 insider-trading
disclosures and one Item 1C cybersecurity disclosure. Counting them gives 16 footnotes instead of
13 — a 23 percent overcount, and three summarization jobs spent on non-footnotes.

THE RULES LIVE IN YAML, NOT IN PYTHON. `metric_definitions/item_disclosure_exclusions.yaml` is the
authority. The list drifts as the SEC adds tagging mandates, and a drifting list embedded in code
means a code change and a deploy for what is really a data update. No issuer name, title, or role
URI is hardcoded here; a condition of the form `if cik == apple` would make the pipeline pass its
tests and fail on every other filer.

NEVER GUESS. A candidate whose namespace this file does not recognise is neither included nor
excluded — it is flagged for review. Silently including inflates the count and spends budget on a
non-footnote; silently excluding drops a real footnote and violates the every-footnote
requirement. Neither is acceptable, so the filing stops for a human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEFINITION = REPO_ROOT / "metric_definitions" / "item_disclosure_exclusions.yaml"

REQUIRED_KEYS = (
    "version",
    "excluded_namespaces",
    "excluded_titles",
    "excluded_role_fragments",
    "unknown_namespace_policy",
    "known_footnote_namespaces",
)


class ExclusionDefinitionError(Exception):
    """The exclusion definition is missing, unparseable, or structurally wrong."""


@dataclass(frozen=True)
class ExclusionVerdict:
    """Why a candidate was excluded, kept, or flagged.

    `rule` and `matched_on` are persisted so a reviewer can answer "why is this not a footnote"
    without re-running the pipeline.
    """

    decision: str  # "footnote" | "excluded" | "review"
    item: str | None = None
    rule: str | None = None
    matched_on: str | None = None

    @property
    def is_excluded(self) -> bool:
        return self.decision == "excluded"

    @property
    def needs_review(self) -> bool:
        return self.decision == "review"

    def as_evidence(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "item": self.item,
            "rule": self.rule,
            "matched_on": self.matched_on,
        }


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    cleaned = text.replace("’", "'").replace("‘", "'")
    cleaned = re.sub(r"[^\w\s'-]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


class ExclusionList:
    """The loaded, validated exclusion definition."""

    def __init__(self, definition: dict[str, Any]) -> None:
        self._definition = definition
        self.version: str = str(definition["version"])

    @classmethod
    def load(cls, path: Path | None = None) -> ExclusionList:
        """Load and validate the definition.

        Parsed with the project's safe YAML reader, the same one that guards the model boundary:
        a definition file is still untrusted input, and `yaml.load` on it would be an arbitrary
        code path opened for a convenience nobody needs.
        """
        from packages.llm_gateway import parse_yaml

        source = path or DEFAULT_DEFINITION
        if not source.is_file():
            raise ExclusionDefinitionError(f"exclusion definition not found: {source}")

        try:
            definition = parse_yaml(source.read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            raise ExclusionDefinitionError(f"{source.name} is not parseable: {error}") from error

        if not isinstance(definition, dict):
            raise ExclusionDefinitionError(f"{source.name} must be a mapping")

        missing = [key for key in REQUIRED_KEYS if key not in definition]
        if missing:
            raise ExclusionDefinitionError(f"{source.name} is missing: {', '.join(missing)}")

        return cls(definition)

    # --- the rules, in the order stage 2 applies them ---------------------------------------

    def _namespace_rule(
        self, role_uri: str | None, namespace: str | None
    ) -> ExclusionVerdict | None:
        haystack = f"{role_uri or ''} {namespace or ''}".lower()
        for entry in self._definition["excluded_namespaces"]:
            prefix = str(entry.get("prefix", "")).lower()
            uri = str(entry.get("uri", "")).lower()
            # `/ecd/` rather than `ecd`, so `recorded` in a role URI is not a namespace match.
            if (prefix and f"/{prefix}/" in haystack) or (uri and uri in haystack):
                return ExclusionVerdict(
                    decision="excluded",
                    item=entry.get("item"),
                    rule="excluded_namespace",
                    matched_on=prefix or uri,
                )
        return None

    def _role_fragment_rule(self, role_uri: str | None) -> ExclusionVerdict | None:
        if not role_uri:
            return None
        lowered = role_uri.lower()
        for entry in self._definition["excluded_role_fragments"]:
            fragment = str(entry.get("fragment", "")).lower()
            if fragment and fragment in lowered:
                return ExclusionVerdict(
                    decision="excluded",
                    item=entry.get("item"),
                    rule="excluded_role_fragment",
                    matched_on=entry.get("fragment"),
                )
        return None

    def _title_rule(self, title: str | None) -> ExclusionVerdict | None:
        normalized = _normalize(title)
        if not normalized:
            return None
        for entry in self._definition["excluded_titles"]:
            match = _normalize(str(entry.get("match", "")))
            if match and match in normalized:
                return ExclusionVerdict(
                    decision="excluded",
                    item=entry.get("item"),
                    rule="excluded_title",
                    matched_on=entry.get("match"),
                )
        return None

    def _is_known_footnote_namespace(self, role_uri: str | None, namespace: str | None) -> bool:
        """True when the candidate sits in a namespace the definition recognises as a footnote.

        An issuer extension role URI — the overwhelming majority, since 91.4 percent of distinct
        tags in the corpus are extensions — is treated as known. Flagging every extension for
        review would stop every filing.
        """
        haystack = f"{role_uri or ''} {namespace or ''}".lower()
        for entry in self._definition["known_footnote_namespaces"]:
            prefix = str(entry.get("prefix", "")).lower()
            uri = str(entry.get("uri", "")).lower()
            if prefix.startswith("<"):
                continue
            if (prefix and f"/{prefix}/" in haystack) or (uri and uri in haystack):
                return True
        # An SEC-hosted taxonomy role that matched no exclusion is a mandate this file does not
        # know about yet. That is exactly the unknown case, and it is not treated as known.
        return "xbrl.sec.gov" not in haystack

    def classify(
        self,
        *,
        title: str | None,
        role_uri: str | None,
        namespace: str | None = None,
    ) -> ExclusionVerdict:
        """Decide whether one stage-1 candidate is a financial-statement footnote.

        Rules are applied namespace, then role fragment, then title — most specific signal first,
        so a verdict cites the strongest evidence available rather than the first that happened to
        match.
        """
        for rule in (
            self._namespace_rule(role_uri, namespace),
            self._role_fragment_rule(role_uri),
            self._title_rule(title),
        ):
            if rule is not None:
                return rule

        if not self._is_known_footnote_namespace(role_uri, namespace):
            policy = self._definition["unknown_namespace_policy"]
            return ExclusionVerdict(
                decision="review",
                rule="unknown_namespace_policy",
                matched_on=str(policy.get("review_state", "REQUIRES_REVIEW")),
            )

        return ExclusionVerdict(decision="footnote", rule="known_footnote_namespace")
