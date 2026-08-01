"""Hardened YAML 1.2 safe parser for model responses.

SECURITY-INVARIANT: model output is untrusted. It is parsed with a YAML 1.2 core-schema safe
loader with explicit resource limits. Arbitrary object construction, custom tags, and unbounded
aliases are rejected.

Why YAML 1.2 specifically, and why ruamel rather than PyYAML:

    PyYAML implements YAML 1.1, whose boolean resolver converts the bare scalars yes, no, on, and
    off into booleans. A filing summary containing a field whose value is the word "no" would
    silently become False. ruamel.yaml in pure safe mode implements the YAML 1.2 core schema,
    where those scalars remain strings. Verified during Sprint 1.

FINANCIAL-INVARIANT: YAML 1.2 parses an unquoted 0000320193 as the integer 320193, destroying the
leading zeros that make it a valid CIK. Every identifier we emit is quoted by the serializer, and
``require_string`` is provided for callers reading identifiers back out.
"""

from __future__ import annotations

import io
import re
from typing import Any, Final

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import YAMLError

from .errors import YamlParseError, YamlSafetyError

MAX_INPUT_BYTES: Final[int] = 4 * 1024 * 1024
MAX_DEPTH: Final[int] = 32
MAX_COLLECTION_SIZE: Final[int] = 10_000
MAX_SCALAR_LENGTH: Final[int] = 1_000_000
MAX_DOCUMENTS: Final[int] = 1

# SECURITY-INVARIANT: alias expansion must be bounded BEFORE parsing.
#
# YAML aliases expand multiplicatively. Measured during Sprint 2: a five-line document with nine
# anchors each referencing the previous nine expanded to 59,049 leaf nodes. Adding two more levels
# exhausts memory. The post-parse size limits below cannot help, because by the time they run the
# expansion has already been allocated.
#
# None of our model-output schemas uses aliases at all, so the bound is deliberately low. A false
# rejection is a loud, cheap failure; an unbounded expansion is a denial of service.
MAX_ANCHORS: Final[int] = 16
MAX_ALIASES: Final[int] = 16

# Conservative textual detection. Over-counting causes a safe rejection; under-counting would
# admit the bomb, so the patterns intentionally do not try to exclude quoted contexts.
_ANCHOR_PATTERN: Final = re.compile(r"(?:^|[\s\[{,])&[A-Za-z_][\w.-]*")
_ALIAS_PATTERN: Final = re.compile(r"(?:^|[\s\[{,])\*[A-Za-z_][\w.-]*")


def _new_loader() -> YAML:
    """Return a YAML 1.2 core-schema safe loader.

    ``pure=True`` forces the Python implementation, which honours the 1.2 core schema. The C
    loader is not used because its resolver behaviour is harder to pin.
    """
    loader = YAML(typ="safe", pure=True)
    loader.allow_duplicate_keys = False
    return loader


def _check_limits(node: Any, depth: int = 0) -> None:
    """Recursively enforce depth, collection-size, and scalar-length limits."""
    if depth > MAX_DEPTH:
        raise YamlSafetyError(f"yaml nesting exceeds maximum depth of {MAX_DEPTH}")
    if isinstance(node, dict):
        if len(node) > MAX_COLLECTION_SIZE:
            raise YamlSafetyError(
                f"yaml mapping has {len(node)} keys, exceeding {MAX_COLLECTION_SIZE}"
            )
        for key, value in node.items():
            _check_limits(key, depth + 1)
            _check_limits(value, depth + 1)
    elif isinstance(node, (list, tuple)):
        if len(node) > MAX_COLLECTION_SIZE:
            raise YamlSafetyError(
                f"yaml sequence has {len(node)} items, exceeding {MAX_COLLECTION_SIZE}"
            )
        for item in node:
            _check_limits(item, depth + 1)
    elif isinstance(node, str):
        if len(node) > MAX_SCALAR_LENGTH:
            raise YamlSafetyError(
                f"yaml scalar of {len(node)} characters exceeds {MAX_SCALAR_LENGTH}"
            )


def _check_alias_budget(text: str) -> None:
    """Reject an alias bomb before the parser can expand it.

    Runs on the raw source, because expansion happens during parsing and any post-parse check is
    already too late.
    """
    anchors = len(_ANCHOR_PATTERN.findall(text))
    if anchors > MAX_ANCHORS:
        raise YamlSafetyError(
            f"yaml document declares {anchors} anchors, exceeding {MAX_ANCHORS}; "
            "alias expansion is bounded to prevent memory exhaustion"
        )
    aliases = len(_ALIAS_PATTERN.findall(text))
    if aliases > MAX_ALIASES:
        raise YamlSafetyError(
            f"yaml document uses {aliases} aliases, exceeding {MAX_ALIASES}; "
            "alias expansion is bounded to prevent memory exhaustion"
        )


def parse_yaml(text: str) -> Any:
    """Parse exactly one YAML 1.2 document from untrusted model output.

    Raises YamlSafetyError when a resource limit is breached, and YamlParseError when the text is
    not valid YAML or contains more than one document.
    """
    if text is None:
        raise YamlParseError("yaml payload is None")
    encoded_length = len(text.encode("utf-8"))
    if encoded_length > MAX_INPUT_BYTES:
        raise YamlSafetyError(f"yaml payload of {encoded_length} bytes exceeds {MAX_INPUT_BYTES}")

    _check_alias_budget(text)

    loader = _new_loader()
    try:
        documents = list(loader.load_all(io.StringIO(text)))
    except DuplicateKeyError as exc:
        raise YamlSafetyError(f"duplicate key in yaml document: {exc}") from exc
    except YAMLError as exc:
        raise YamlParseError(f"invalid yaml: {exc}") from exc

    if len(documents) > MAX_DOCUMENTS:
        raise YamlSafetyError(f"expected {MAX_DOCUMENTS} yaml document, found {len(documents)}")
    if not documents:
        raise YamlParseError("yaml payload contained no document")

    document = documents[0]
    _check_limits(document)
    return document


def require_mapping(document: Any) -> dict[str, Any]:
    """Return the document as a mapping, or raise."""
    if not isinstance(document, dict):
        raise YamlParseError(
            f"expected a yaml mapping at the document root, got {type(document).__name__}"
        )
    return document


def require_string(mapping: dict[str, Any], key: str) -> str:
    """Return a required string field, rejecting values coerced to another type.

    FINANCIAL-INVARIANT: a CIK or accession that arrives as an int means the producer failed to
    quote it and leading zeros are already lost. That is unrecoverable, so it is an error rather
    than something to coerce back.
    """
    if key not in mapping:
        raise YamlParseError(f"missing required field: {key}")
    value = mapping[key]
    if not isinstance(value, str):
        raise YamlParseError(
            f"field {key!r} must be a quoted string, got {type(value).__name__} "
            f"({value!r}); identifiers must be quoted in YAML"
        )
    return value
