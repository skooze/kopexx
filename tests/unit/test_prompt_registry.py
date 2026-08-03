"""Versioned prompts, and the edit this package exists to make impossible.

HERMETIC. Every synthetic case builds its own prompt directory under `tmp_path` — a manifest, one
or two .txt files, nothing else. Nothing reaches a network, a credential or a model. The tests that
read the repository's own `prompts/parser` directory are gathered at the bottom, separated from the
synthetic ones, and they check the committed contract rather than any particular wording.

WHAT IS ACTUALLY BEING TESTED. Not that a loader returns a record; that is arithmetic. The subject
is the set of things this registry must REFUSE: a prompt file whose bytes moved after its hash was
recorded, a manifest entry naming a file outside the prompt directory, one identity resolving to
two sets of bytes, two ACTIVE prompts competing for a role, and a caller asking for "the latest"
instead of a version a later reader can reproduce.

WHY THE HASHES HERE ARE COMPUTED WITH `hashlib` DIRECTLY. The registry hashes with
`packages.storage.sha256_text`. A test that recorded its expectations with the same helper would
agree with the subject by construction and prove nothing about either. These tests hash the bytes
on disk independently, which is also what a reviewer with `sha256sum` would do.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import Any

import pytest

from packages.llm_gateway import parse_yaml, require_mapping
from packages.prompt_registry import (
    PromptFormatError,
    PromptIntegrityError,
    PromptNotFoundError,
    PromptRegistry,
    PromptRegistryError,
    PromptVersion,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_PARSER_DIRECTORY = REPO_ROOT / "prompts" / "parser"

REQUIRED_FIELDS = ("prompt_id", "version", "file", "sha256", "created", "status", "role")

PROMPT_TEXT = (
    "Read the filing below and report its structure in the filing's own vocabulary.\n"
    "Impose no taxonomy of your own.\n"
)


# --- synthetic prompt directories ----------------------------------------------------------------


def sha256_of(path: Path) -> str:
    """Hash the bytes actually on disk, with no help from the code under test."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_prompt(directory: Path, filename: str, text: str) -> str:
    """Write one prompt file and return the SHA-256 a manifest would have to record."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(text.encode("utf-8"))
    return sha256_of(path)


def entry(**overrides: Any) -> dict[str, Any]:
    """One manifest entry. Every field the loader requires, none of them from a real prompt."""
    fields: dict[str, Any] = {
        "prompt_id": "parser-complete-filing",
        "version": "1",
        "file": "parser-v1.txt",
        "sha256": "0" * 64,
        "created": "2026-08-03",
        "status": "ACTIVE",
        "role": "parsing",
    }
    fields.update(overrides)
    return fields


def render(fields: dict[str, Any]) -> str:
    lines = []
    for index, (key, value) in enumerate(fields.items()):
        prefix = "  - " if index == 0 else "    "
        lines.append(f"{prefix}{key}: " + ("null" if value is None else f'"{value}"'))
    return "\n".join(lines) + "\n"


def manifest(*entries: dict[str, Any]) -> str:
    return 'schema_version: "prompt-versions-v1"\n\nprompts:\n' + "".join(
        render(fields) for fields in entries
    )


def write_manifest(directory: Path, text: str, *, name: str = "versions.yaml") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")
    return directory


def one_version(directory: Path, *, text: str = PROMPT_TEXT, **overrides: Any) -> Path:
    """A prompt directory holding a single, correctly recorded, ACTIVE version."""
    digest = write_prompt(directory, "parser-v1.txt", text)
    write_manifest(directory, manifest(entry(sha256=digest, **overrides)))
    return directory


# --- loading a version whose bytes still match --------------------------------------------------


def test_a_version_loads_when_its_bytes_match_the_recorded_hash(tmp_path: Path) -> None:
    """The whole registry rests on this: bytes on disk, hash in the manifest, and they agree.

    The text is carried on the record rather than left as a path for the caller to re-read, so the
    bytes that were verified are the bytes an invocation sends.
    """
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts"))
    version = registry.get("parser-complete-filing", "1")

    assert version.identity == "parser-complete-filing@1"
    assert version.text == PROMPT_TEXT
    assert version.filename == "parser-v1.txt"
    assert version.role == "parsing"
    assert version.status == "ACTIVE"
    assert version.sha256 == sha256_of(tmp_path / "prompts" / "parser-v1.txt")


def test_rewriting_a_prompt_with_identical_bytes_still_loads(tmp_path: Path) -> None:
    """ANTI-VACUITY for the integrity guard: it watches BYTES, not timestamps or edit events.

    A guard keyed on mtime would reject this and would have to be worked around by anyone who
    touched a file, which is how an immutability check gets disabled.
    """
    root = one_version(tmp_path / "prompts")
    (root / "parser-v1.txt").write_bytes(PROMPT_TEXT.encode("utf-8"))

    assert PromptRegistry.from_directory(root).get("parser-complete-filing", "1").text == (
        PROMPT_TEXT
    )


# --- the immutability guard ---------------------------------------------------------------------


def test_editing_a_prompt_after_recording_its_hash_is_refused(tmp_path: Path) -> None:
    """THE IMMUTABILITY GUARD. Every stored invocation records the prompt version it used.

    Editing that version in place retroactively changes what all of them claim to have asked, and
    nothing downstream could detect it. The refusal has to name both hashes — otherwise a reader
    cannot tell an edit from a corrupted checkout — and it has to say what to do instead, because a
    developer blocked by an unexplained error edits the manifest hash rather than adding a version.
    """
    root = one_version(tmp_path / "prompts")
    recorded = sha256_of(root / "parser-v1.txt")
    edited = PROMPT_TEXT + "Also, prefer short answers.\n"
    (root / "parser-v1.txt").write_bytes(edited.encode("utf-8"))

    with pytest.raises(PromptIntegrityError) as error:
        PromptRegistry.from_directory(root)

    message = str(error.value)
    assert recorded in message, "the refusal must name the hash the manifest recorded"
    assert hashlib.sha256(edited.encode("utf-8")).hexdigest() in message
    assert "NEW version" in message, "the reader must be told to add a version, not fix the hash"
    assert "new manifest entry" in message


def test_a_single_added_newline_is_an_edit(tmp_path: Path) -> None:
    """MUTATION. The guard compares bytes, not meaning, so whitespace is not exempt.

    A prompt is sent to a model verbatim, and a tolerance for "insignificant" changes is exactly
    the tolerance under which a paragraph eventually moves.
    """
    root = one_version(tmp_path / "prompts")
    (root / "parser-v1.txt").write_bytes((PROMPT_TEXT + "\n").encode("utf-8"))

    with pytest.raises(PromptIntegrityError):
        PromptRegistry.from_directory(root)


def test_a_hash_nobody_computed_is_refused(tmp_path: Path) -> None:
    """A manifest entry with a placeholder or hand-typed hash must fail loudly at load.

    The failure mode this prevents is a version added with the hash field filled in later — which
    is to say never — leaving one entry in the manifest that proves nothing.
    """
    write_prompt(tmp_path / "prompts", "parser-v1.txt", PROMPT_TEXT)
    write_manifest(tmp_path / "prompts", manifest(entry(sha256="0" * 64)))

    with pytest.raises(PromptIntegrityError):
        PromptRegistry.from_directory(tmp_path / "prompts")


# --- the manifest is mandatory ------------------------------------------------------------------


def test_a_prompt_directory_without_a_manifest_is_refused(tmp_path: Path) -> None:
    """A directory listing is not a record. Without a manifest nothing can prove a file is intact.

    Falling back to "load whatever .txt files are here" would make the registry an elaborate
    `read_text`, and the immutability guarantee would quietly become nothing.
    """
    write_prompt(tmp_path / "prompts", "parser-v1.txt", PROMPT_TEXT)

    with pytest.raises(PromptNotFoundError) as error:
        PromptRegistry.from_directory(tmp_path / "prompts")

    assert "versions.yaml" in str(error.value), "the refusal must name the file it looked for"


def test_the_manifest_name_is_a_parameter_not_a_hardcoded_string(tmp_path: Path) -> None:
    """ANTI-VACUITY for the test above: the refusal is about absence, not about a fixed filename."""
    digest = write_prompt(tmp_path / "prompts", "parser-v1.txt", PROMPT_TEXT)
    write_manifest(tmp_path / "prompts", manifest(entry(sha256=digest)), name="prompt-index.yaml")

    registry = PromptRegistry.from_directory(
        tmp_path / "prompts", manifest_name="prompt-index.yaml"
    )
    assert registry.versions[0].identity == "parser-complete-filing@1"


def test_the_registry_knows_no_directory_of_its_own() -> None:
    """The path is SUPPLIED and has no default, for the same reason the snapshot path has none.

    A default path is how a stale artifact keeps answering after the real one has moved: the caller
    that forgot to pass a directory gets a plausible answer instead of an error.
    """
    directory = inspect.signature(PromptRegistry.from_directory).parameters["directory"]
    assert directory.default is inspect.Parameter.empty


def test_a_declared_file_that_is_not_on_disk_is_refused(tmp_path: Path) -> None:
    """A manifest that promises a version the directory does not hold is broken, not partial.

    Skipping the missing entry would let a registry load with a role silently unfilled, and the
    first symptom would be a refusal to run, far from the cause.
    """
    write_prompt(tmp_path / "prompts", "parser-v1.txt", PROMPT_TEXT)
    write_manifest(tmp_path / "prompts", manifest(entry(file="parser-v2.txt")))

    with pytest.raises(PromptNotFoundError) as error:
        PromptRegistry.from_directory(tmp_path / "prompts")

    assert "parser-v2.txt" in str(error.value)


# --- the path guard -------------------------------------------------------------------------------


def test_a_manifest_entry_that_escapes_the_prompt_directory_is_refused(tmp_path: Path) -> None:
    """SECURITY-INVARIANT: a manifest entry names a file INSIDE the prompt directory.

    The target here EXISTS and its hash is recorded correctly, so the refusal can only come from
    the traversal check — not from the missing-file branch, which would make this test pass while
    proving nothing. A prompt is model-visible content; a manifest that can name any path on the
    host is an exfiltration primitive wearing a configuration file.
    """
    secret = tmp_path / "secret.txt"
    secret.write_bytes(b"a credential that must never reach a model\n")
    root = tmp_path / "prompts"
    root.mkdir()
    write_manifest(root, manifest(entry(file="../secret.txt", sha256=sha256_of(secret))))

    with pytest.raises(PromptFormatError) as error:
        PromptRegistry.from_directory(root)

    assert "escapes" in str(error.value)
    assert "credential" not in str(error.value), "a refusal must not quote the file it refused"


def test_an_absolute_path_in_the_manifest_is_refused(tmp_path: Path) -> None:
    """Joining an absolute path onto a root discards the root entirely.

    `Path('/prompts') / '/etc/x'` is `/etc/x`. A guard written as "reject strings containing .."
    would miss this, so the check is on the resolved location rather than on the spelling.
    """
    outside = tmp_path / "outside.txt"
    outside.write_bytes(PROMPT_TEXT.encode("utf-8"))
    root = tmp_path / "prompts"
    root.mkdir()
    write_manifest(root, manifest(entry(file=str(outside), sha256=sha256_of(outside))))

    with pytest.raises(PromptFormatError, match="escapes"):
        PromptRegistry.from_directory(root)


def test_a_symlink_out_of_the_prompt_directory_is_refused(tmp_path: Path) -> None:
    """The check resolves the path, so a link inside the directory cannot smuggle in a file.

    A guard that only inspected the manifest string would admit this: `parser-v1.txt` is a perfectly
    ordinary relative name right up until you follow it.
    """
    outside = tmp_path / "outside.txt"
    outside.write_bytes(PROMPT_TEXT.encode("utf-8"))
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "parser-v1.txt").symlink_to(outside)
    write_manifest(root, manifest(entry(sha256=sha256_of(outside))))

    with pytest.raises(PromptFormatError, match="escapes"):
        PromptRegistry.from_directory(root)


def test_a_subdirectory_inside_the_prompt_directory_is_permitted(tmp_path: Path) -> None:
    """ANTI-VACUITY for the traversal guard: it refuses ESCAPES, not every path separator.

    A guard that rejected any `/` would be a guard nobody could live with, and the version that
    replaced it would be the one written in a hurry.
    """
    root = tmp_path / "prompts"
    digest = write_prompt(root / "v1", "parser.txt", PROMPT_TEXT)
    write_manifest(root, manifest(entry(file="v1/parser.txt", sha256=digest)))

    registry = PromptRegistry.from_directory(root)
    assert registry.get("parser-complete-filing", "1").text == PROMPT_TEXT


# --- one identity, one set of bytes ---------------------------------------------------------------


def test_a_duplicate_prompt_id_and_version_is_refused(tmp_path: Path) -> None:
    """An identity is what a run record quotes. It must resolve to exactly one set of bytes.

    Two entries sharing `prompt-id@version` would make a stored invocation unreproducible while
    looking completely ordinary, and a first-match-wins loader would pick between them in silence.
    """
    root = tmp_path / "prompts"
    first = write_prompt(root, "parser-v1.txt", PROMPT_TEXT)
    second = write_prompt(root, "parser-v1-again.txt", PROMPT_TEXT + "and again\n")
    write_manifest(
        root,
        manifest(
            entry(sha256=first),
            entry(file="parser-v1-again.txt", sha256=second, status="SUPERSEDED"),
        ),
    )

    with pytest.raises(PromptFormatError) as error:
        PromptRegistry.from_directory(root)

    assert "parser-complete-filing@1" in str(error.value)


def test_two_versions_of_one_prompt_are_not_a_duplicate(tmp_path: Path) -> None:
    """ANTI-VACUITY. Adding a version is the SUPPORTED way to change a prompt.

    If the duplicate check flagged this, the only remaining way to change a prompt would be to edit
    one in place — the exact act the registry exists to prevent.
    """
    root = tmp_path / "prompts"
    first = write_prompt(root, "parser-v1.txt", PROMPT_TEXT)
    second = write_prompt(root, "parser-v2.txt", PROMPT_TEXT + "Quote your sources verbatim.\n")
    write_manifest(
        root,
        manifest(
            entry(sha256=first, status="SUPERSEDED", superseded_by="2"),
            entry(version="2", file="parser-v2.txt", sha256=second, supersedes="1"),
        ),
    )

    registry = PromptRegistry.from_directory(root)
    assert [v.identity for v in registry.versions] == [
        "parser-complete-filing@1",
        "parser-complete-filing@2",
    ]


def test_a_superseded_version_is_kept_and_still_resolvable(tmp_path: Path) -> None:
    """History is recorded forward and never deleted.

    A superseded prompt is evidence: invocations were paid for under it and may be acted on. It
    stops being ACTIVE; it does not stop existing, and `get` must still return its exact bytes.
    """
    root = tmp_path / "prompts"
    first = write_prompt(root, "parser-v1.txt", PROMPT_TEXT)
    second = write_prompt(root, "parser-v2.txt", PROMPT_TEXT + "Quote your sources verbatim.\n")
    write_manifest(
        root,
        manifest(
            entry(sha256=first, status="SUPERSEDED", superseded_by="2"),
            entry(version="2", file="parser-v2.txt", sha256=second, supersedes="1"),
        ),
    )

    registry = PromptRegistry.from_directory(root)
    old = registry.get("parser-complete-filing", "1")

    assert old.text == PROMPT_TEXT, "the historical bytes are still exactly what they were"
    assert old.superseded_by == "2"
    assert registry.get("parser-complete-filing", "2").supersedes == "1"
    assert registry.active_for("parsing").version == "2"


# --- choosing a version ---------------------------------------------------------------------------


def test_get_requires_an_exact_version(tmp_path: Path) -> None:
    """A version that was never declared is an error, not a near miss to round to.

    The refusal names what does exist so the reader can see whether they mistyped a version or are
    pointed at the wrong directory entirely.
    """
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts"))

    with pytest.raises(PromptNotFoundError) as error:
        registry.get("parser-complete-filing", "2")

    assert "parser-complete-filing@1" in str(error.value)


def test_there_is_deliberately_no_latest(tmp_path: Path) -> None:
    """A caller that asked for 'the latest' has recorded nothing a later reader can reproduce.

    `active_for` exists for choosing one, and what it returns carries a version number. This asserts
    the absence directly, because the convenience method is the one somebody adds without noticing
    it removes the reproducibility the rest of the package is built for.
    """
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts"))

    assert not [name for name in dir(registry) if "latest" in name.lower()]
    assert "@" in registry.active_for("parsing").identity


def test_get_matches_on_prompt_id_and_version_together(tmp_path: Path) -> None:
    """MUTATION. Two prompts may share a version number; only the pair identifies bytes.

    A lookup that matched on version alone would return the summary prompt to a parser run, and
    both records would look entirely well-formed.
    """
    root = tmp_path / "prompts"
    parser = write_prompt(root, "parser-v1.txt", PROMPT_TEXT)
    summary = write_prompt(root, "summary-v1.txt", "Summarize the node you are given.\n")
    write_manifest(
        root,
        manifest(
            entry(sha256=parser),
            entry(prompt_id="summary-node", file="summary-v1.txt", sha256=summary, role="summary"),
        ),
    )

    registry = PromptRegistry.from_directory(root)
    assert registry.get("parser-complete-filing", "1").text == PROMPT_TEXT
    assert registry.get("summary-node", "1").text.startswith("Summarize")


# --- active_for -------------------------------------------------------------------------------------


def test_active_for_returns_the_single_active_version(tmp_path: Path) -> None:
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts"))
    active = registry.active_for("parsing")

    assert active.identity == "parser-complete-filing@1"
    assert active.status == "ACTIVE"


def test_active_for_refuses_a_role_with_no_active_version(tmp_path: Path) -> None:
    """A role whose only prompt is retired has no prompt, and must say so rather than improvise.

    The declared-but-superseded case is used deliberately: a check that only asked "is this role
    mentioned anywhere" would pass here and hand a run a prompt that was withdrawn.
    """
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts", status="SUPERSEDED"))

    with pytest.raises(PromptNotFoundError) as error:
        registry.active_for("parsing")

    assert "parsing" in str(error.value)


def test_active_for_refuses_when_two_versions_are_active(tmp_path: Path) -> None:
    """Two ACTIVE prompts for one role is a configuration error, not a preference to resolve.

    Picking between them here would make the choice invisible in the run record: two runs would
    quote different prompts from the same manifest with nothing to explain the difference. The
    refusal names both so a human can retire one.
    """
    root = tmp_path / "prompts"
    first = write_prompt(root, "parser-v1.txt", PROMPT_TEXT)
    second = write_prompt(root, "parser-v2.txt", PROMPT_TEXT + "Quote your sources verbatim.\n")
    write_manifest(
        root,
        manifest(
            entry(sha256=first),
            entry(version="2", file="parser-v2.txt", sha256=second),
        ),
    )

    registry = PromptRegistry.from_directory(root)
    with pytest.raises(PromptFormatError) as error:
        registry.active_for("parsing")

    message = str(error.value)
    assert "parser-complete-filing@1" in message
    assert "parser-complete-filing@2" in message
    assert "product decision" in message


def test_two_active_prompts_in_different_roles_are_not_a_conflict(tmp_path: Path) -> None:
    """ANTI-VACUITY. The four roles are independent, and none inherits another's prompt.

    If this were flagged, a parser-only run and a summary run could never be configured together,
    and the ambiguity check would have to be deleted rather than narrowed.
    """
    root = tmp_path / "prompts"
    parser = write_prompt(root, "parser-v1.txt", PROMPT_TEXT)
    summary = write_prompt(root, "summary-v1.txt", "Summarize the node you are given.\n")
    write_manifest(
        root,
        manifest(
            entry(sha256=parser),
            entry(prompt_id="summary-node", file="summary-v1.txt", sha256=summary, role="summary"),
        ),
    )

    registry = PromptRegistry.from_directory(root)
    assert registry.active_for("parsing").prompt_id == "parser-complete-filing"
    assert registry.active_for("summary").prompt_id == "summary-node"


def test_a_role_that_was_never_declared_is_a_refusal_not_a_fallback(tmp_path: Path) -> None:
    """No silent substitution. A run with no prompt for its role stops; it does not borrow one."""
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts"))

    with pytest.raises(PromptNotFoundError, match="image"):
        registry.active_for("image")


def test_status_is_compared_exactly(tmp_path: Path) -> None:
    """A status the registry does not recognise never becomes ACTIVE by resemblance.

    The failure direction matters: a mistyped status refuses the run rather than activating a
    version nobody meant to activate. Loosening this to a case-insensitive or prefix match would
    invert that.
    """
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts", status="active"))

    with pytest.raises(PromptNotFoundError):
        registry.active_for("parsing")


# --- manifest format --------------------------------------------------------------------------------


@pytest.mark.parametrize("missing", REQUIRED_FIELDS)
def test_a_manifest_entry_missing_a_required_field_is_refused(tmp_path: Path, missing: str) -> None:
    """Every field is provenance. A half-recorded version is a claim nobody can check.

    The refusal names the field, because a manifest with a dozen entries is otherwise a search.
    """
    root = tmp_path / "prompts"
    digest = write_prompt(root, "parser-v1.txt", PROMPT_TEXT)
    fields = entry(sha256=digest)
    del fields[missing]
    write_manifest(root, manifest(fields))

    with pytest.raises(PromptFormatError, match=missing):
        PromptRegistry.from_directory(root)


def test_a_manifest_entry_with_every_required_field_is_accepted(tmp_path: Path) -> None:
    """ANTI-VACUITY for the parametrized test above: the complete entry is the one that loads."""
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts"))
    assert len(registry.versions) == 1


@pytest.mark.parametrize(
    "text",
    [
        'schema_version: "prompt-versions-v1"\nprompts: []\n',
        'schema_version: "prompt-versions-v1"\n',
        'schema_version: "prompt-versions-v1"\nprompts:\n',
    ],
)
def test_a_manifest_declaring_no_prompts_is_refused(tmp_path: Path, text: str) -> None:
    """An empty registry would answer every question with "not found" and report a clean load.

    Three spellings are checked: an explicit empty sequence, the key absent entirely, and a key with
    no value, which YAML resolves to null rather than to a list.
    """
    root = tmp_path / "prompts"
    write_prompt(root, "parser-v1.txt", PROMPT_TEXT)
    write_manifest(root, text)

    with pytest.raises(PromptFormatError, match="no prompts"):
        PromptRegistry.from_directory(root)


def test_a_prompts_element_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    """A bare string under `prompts` is a manifest somebody half-edited; index it in the error."""
    root = tmp_path / "prompts"
    write_prompt(root, "parser-v1.txt", PROMPT_TEXT)
    write_manifest(root, 'schema_version: "prompt-versions-v1"\nprompts:\n  - parser-v1.txt\n')

    with pytest.raises(PromptFormatError, match=r"prompts\[0\]"):
        PromptRegistry.from_directory(root)


def test_optional_supersession_fields_default_to_absent(tmp_path: Path) -> None:
    """A first version supersedes nothing, and absence must read as absence rather than as "None".

    `supersedes: null` and an omitted key mean the same thing, and both have to arrive as None so a
    reviewer reading a chain can tell where it starts.
    """
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts"))
    version = registry.get("parser-complete-filing", "1")

    assert version.supersedes is None
    assert version.superseded_by is None
    assert version.note == ""


def test_an_explicit_null_supersession_field_is_also_absent(tmp_path: Path) -> None:
    registry = PromptRegistry.from_directory(
        one_version(tmp_path / "prompts", supersedes=None, superseded_by=None)
    )
    version = registry.get("parser-complete-filing", "1")

    assert (version.supersedes, version.superseded_by) == (None, None)


# --- the record a run quotes -------------------------------------------------------------------------


def test_identity_is_prompt_id_at_version() -> None:
    """`prompt-id@version` is the string a run record quotes and a reviewer compares.

    It is asserted on a directly constructed record as well as on a loaded one, because the format
    is a contract with the run log rather than an artifact of how the manifest is parsed.
    """
    version = PromptVersion(
        prompt_id="parser-complete-filing",
        version="1",
        filename="parser-v1.txt",
        sha256="0" * 64,
        created="2026-08-03",
        status="ACTIVE",
        role="parsing",
        text=PROMPT_TEXT,
    )
    assert version.identity == "parser-complete-filing@1"


def test_the_run_record_carries_the_hash_and_not_the_prompt_text(tmp_path: Path) -> None:
    """A record proves WHICH prompt ran; copying the bytes into it would create a second home.

    The hash plus the identity is enough to fetch the exact text from the registry. A copy in a
    stored record is a duplicate that drifts, and drifted duplicates are what this package exists
    to prevent.
    """
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts"))
    record = registry.get("parser-complete-filing", "1").to_mapping()

    assert record["prompt_id"] == "parser-complete-filing"
    assert record["version"] == "1"
    assert record["sha256"] == sha256_of(tmp_path / "prompts" / "parser-v1.txt")
    assert record["status"] == "ACTIVE"
    assert record["role"] == "parsing"
    assert "text" not in record
    assert PROMPT_TEXT not in str(record)


def test_a_loaded_version_is_immutable_in_memory_as_well(tmp_path: Path) -> None:
    """A verified record that a caller can edit is a verified record for exactly one statement."""
    registry = PromptRegistry.from_directory(one_version(tmp_path / "prompts"))
    version = registry.get("parser-complete-filing", "1")

    with pytest.raises(AttributeError):
        version.text = "something else"  # type: ignore[misc]


@pytest.mark.parametrize("error", [PromptFormatError, PromptIntegrityError, PromptNotFoundError])
def test_every_refusal_is_catchable_as_one_family(error: type[Exception]) -> None:
    """A caller wrapping prompt loading needs one except clause, or it will miss the new one."""
    assert issubclass(error, PromptRegistryError)
    assert issubclass(PromptRegistryError, Exception)


# --- the committed parser prompt directory ------------------------------------------------------------


def test_the_committed_parser_prompt_directory_loads() -> None:
    """The directory the product ships with must satisfy its own registry.

    This is the test that fails if somebody edits the shipped prompt in place: the manifest records
    a hash, the loader recomputes it, and the two have to agree in CI as well as on a laptop.
    """
    registry = PromptRegistry.from_directory(COMMITTED_PARSER_DIRECTORY)

    assert registry.versions, "the committed parser manifest declares no prompt versions"
    for version in registry.versions:
        assert version.text.strip(), f"{version.identity} is an empty prompt"
        assert (COMMITTED_PARSER_DIRECTORY / version.filename).is_file()


def test_the_committed_declared_hash_matches_the_bytes_on_disk() -> None:
    """Checked against the RAW BYTES, which is stricter than the loader itself manages.

    The registry hashes the decoded text, so a line-ending conversion — CRLF is what a Windows
    editor writes on save — could move the bytes on disk without moving the hash the loader
    computes. Hashing the file the way `sha256sum` and Git see it closes that gap, and keeps the
    manifest independently verifiable by a reviewer with no Python at all.
    """
    manifest_document = require_mapping(
        parse_yaml((COMMITTED_PARSER_DIRECTORY / "versions.yaml").read_text(encoding="utf-8"))
    )
    declared = manifest_document["prompts"]
    assert declared, "the committed manifest declares nothing, so this guard would check nothing"

    for record in declared:
        path = COMMITTED_PARSER_DIRECTORY / str(record["file"])
        assert sha256_of(path) == str(record["sha256"]), (
            f"{record['file']} no longer hashes to the value the manifest records. "
            "A prompt version is never edited after it has been used: add a NEW version."
        )


def test_the_committed_directory_declares_one_active_prompt_per_role() -> None:
    """Whatever the manifest grows to, a role must never end up with two prompts competing.

    Asserted over the roles the manifest actually declares rather than a hardcoded list, so adding
    a summary or image prompt extends the guard instead of walking around it.
    """
    registry = PromptRegistry.from_directory(COMMITTED_PARSER_DIRECTORY)
    active_roles = {v.role for v in registry.versions if v.status == "ACTIVE"}
    assert active_roles, "no committed prompt version is ACTIVE"

    for role in active_roles:
        active = registry.active_for(role)
        assert active.status == "ACTIVE"
        assert registry.get(active.prompt_id, active.version) is active


def test_the_committed_parsing_prompt_is_the_one_a_parser_run_would_load() -> None:
    """ONLY THE PARSING MODEL IS REQUIRED, so the parsing prompt is the one that must resolve.

    A parser-only run is a complete, valid run and is the first workflow built; if `active_for` on
    the parsing role cannot answer from the shipped directory, nothing else in Phase 2 can start.
    """
    active = PromptRegistry.from_directory(COMMITTED_PARSER_DIRECTORY).active_for("parsing")

    assert active.identity.endswith(f"@{active.version}")
    assert active.identity.startswith(f"{active.prompt_id}@")
    assert active.created, "an ACTIVE prompt with no creation date is unrecorded evidence"
    assert active.text.strip()
