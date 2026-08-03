"""Coverage validation: proving a parse against the preserved bytes, and refusing to overclaim.

HERMETIC. Nothing here reaches a network, a model, a credential or a database. The only files read
are committed original SEC source under `tests/fixtures/filings/`, which is exactly the material
this package exists to prove things against — a resolution test written entirely against synthetic
prose would never meet a sentence wrapped across three lines with irregular indentation, or a
sentence cut into six pieces by inline-XBRL markup, and those are the two cases that decide whether
a citation rate means anything.

WHAT IS ACTUALLY BEING TESTED. Not that a reader reads and a search searches. The subject is the
set of things this package must REFUSE to do: refuse to own a vocabulary of node types, refuse to
drop the key it did not expect, refuse to turn a missing envelope key into a lost measurement,
refuse to call a quote occurring everywhere `located`, refuse to read meaning out of a number, and
above all refuse to issue COMPLETE — the strongest verdict available is REVIEW_REQUIRED, because
nothing measured here establishes that every human-readable source range is represented.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from packages.coverage_validation import (
    AMBIGUITY_THRESHOLD,
    PROVISIONAL_ENVELOPE_KEYS,
    RESOLVED,
    ArtifactIndex,
    Resolution,
    ResponseUnreadableError,
    ValidationStatus,
    extract_numbers,
    read,
    validate_response,
)
from packages.coverage_validation.numbers import assess

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPO_ROOT / "packages" / "coverage_validation"

#: The pre-2001 complete submission: wrapped, double-spaced, unmarked ASCII prose.
PRE_2001 = ("0000320193-94-000016", "0000320193-94-000016.txt")
#: An inline-XBRL primary document: prose and figures cut apart by span and ix elements.
INLINE_XBRL = ("0000320193-25-000073", "aapl-20250628.htm")


def preserved(fixtures_dir: Path, filing: tuple[str, str]) -> str:
    """The decoded text of one committed original SEC document, exactly as it is stored."""
    accession, filename = filing
    path = fixtures_dir / "filings" / accession / filename
    return path.read_text(encoding="utf-8", errors="replace")


def response(*, nodes: str = "", unresolved: str = "", omit: tuple[str, ...] = ()) -> str:
    """One provisional-envelope response, in the only syntax the boundary permits.

    `omit` drops an envelope key entirely, which is how a model that ignored half the instruction
    is simulated. `nodes` and `unresolved` are pre-indented blocks.
    """
    blocks = {
        "artifact": "artifact:\n  format: parsed-filing\n",
        "document": "document:\n  - filename: filing.htm\n",
        "nodes": "nodes:\n" + nodes,
        "unresolved": "unresolved:\n" + unresolved,
        "metadata": "metadata:\n  model: a model label\n",
    }
    return "".join(text for key, text in blocks.items() if key not in omit)


def block(body: str) -> str:
    """Indent a hand-written YAML fragment to sit under an envelope key."""
    return textwrap.indent(textwrap.dedent(body).strip("\n") + "\n", "  ")


ONE_ARTIFACT = {"filing.htm": "Total net sales increased 2 percent during the quarter to 94,036."}

CITING_NODE = block(
    """
    - id: n1
      order: 1
      type: A LABEL THE MODEL CHOSE FOR ITSELF
      title: Net sales
      content: Net sales rose to 94,036.
      source:
        - filename: filing.htm
          quote: Total net sales increased 2 percent
    """
)


# --- the reader owns no vocabulary ---------------------------------------------------------------


def test_a_node_type_no_backend_ontology_contains_survives_untouched() -> None:
    """rules.md section 21: the selected parsing model decides what a filing means.

    A reader that validated `type` against an enum would be a backend semantic parser wearing a
    smaller hat, and the label it rejected is precisely the observation Phase 2 was run to make.
    """
    document = read(
        response(
            nodes=block(
                """
                - id: n1
                  type: SUPPLEMENTAL UNAUDITED PRO FORMA COMMENTARY
                  title: Note 7 - Segment Information
                """
            )
        )
    )
    node = document.nodes[0]
    assert node.node_type == "SUPPLEMENTAL UNAUDITED PRO FORMA COMMENTARY"
    assert node.title == "Note 7 - Segment Information"
    assert document.types_used() == {"SUPPLEMENTAL UNAUDITED PRO FORMA COMMENTARY": 1}


def test_an_unrecognised_node_key_is_preserved_rather_than_dropped() -> None:
    """The point of the first experiments is to find out what models actually emit.

    A reader that silently discarded the surprising half of a response would guarantee the
    surprise was never seen, and the response was bought and cannot be regenerated for free.
    """
    document = read(
        response(
            nodes=block(
                """
                - id: n1
                  title: A title
                  parse_note: the model invented this key on its own
                  chunk_index: 3
                """
            )
        )
    )
    assert document.nodes[0].extra == {
        "parse_note": "the model invented this key on its own",
        "chunk_index": 3,
    }


def test_a_known_node_key_is_not_also_dumped_into_extra() -> None:
    """MUTATION. The preservation test above passes vacuously if `extra` is just the whole node.

    `extra` has to be the complement of what the reader understood, otherwise every field would be
    reported twice and `extra` would stop being evidence that a model emitted something new.
    """
    document = read(
        response(
            nodes=block(
                """
                - id: n1
                  order: 1
                  type: A TYPE
                  title: A title
                  content: Some content.
                  confidence: high
                  parse_note: the one key nobody defined
                """
            )
        )
    )
    extra = document.nodes[0].extra
    assert set(extra) == {"parse_note"}
    for known in ("id", "order", "type", "title", "content", "confidence"):
        assert known not in extra, f"{known} is a key the reader understood; it is not a surprise"


def test_a_missing_envelope_key_is_reported_not_raised() -> None:
    """A response that omits a key is EVIDENCE about the prompt or the model.

    Refusing it would throw the measurement away, and the response has already been paid for. The
    absence is a finding carried forward to a reviewer, never a refusal.
    """
    document = read(response(nodes=CITING_NODE, omit=("metadata", "artifact")))
    assert document.missing_envelope_keys == ("artifact", "metadata")
    assert document.node_count == 1, "the rest of the response is still read"


def test_a_complete_envelope_reports_nothing_missing() -> None:
    """MUTATION. The test above proves nothing if `missing_envelope_keys` is never empty.

    It also pins the reported set to the provisional envelope the package publishes, so a key
    added there cannot start being silently reported as missing by a stale copy of the tuple.
    """
    document = read(response(nodes=CITING_NODE))
    assert document.missing_envelope_keys == ()
    assert set(PROVISIONAL_ENVELOPE_KEYS) == {
        "artifact",
        "document",
        "nodes",
        "unresolved",
        "metadata",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a sentence the model wrote instead of a parse", "rather than a mapping"),
        ("- one\n- two\n", "rather than a mapping"),
        ("nodes: [unclosed\n", "not one YAML 1.2 document"),
    ],
)
def test_a_response_that_is_not_one_yaml_mapping_is_unreadable(text: str, expected: str) -> None:
    """The single case the reader may refuse: there is no document to read generically.

    Everything softer than this — no nodes, no titles, half an envelope — is a finding. This is
    the boundary between the two, and the message has to say which side it failed on so a reviewer
    can tell a chatty model apart from a broken one.
    """
    with pytest.raises(ResponseUnreadableError) as error:
        read(text)
    assert expected in str(error.value)


def test_the_document_counts_only_what_the_model_actually_emitted() -> None:
    """Counts are a census of the response, not a target the reader helps a model reach.

    A reference with neither a quote nor a filename locates nothing and is not counted as a
    citation; counting it would inflate the reference total with empty locators.
    """
    document = read(
        response(
            nodes=block(
                """
                - id: n1
                  image: true
                  tables:
                    - rows:
                        - [Americas, 40315]
                  source:
                    - filename: filing.htm
                      quote: Total net sales
                    - confidence: high
                - id: n2
                """
            )
        )
    )
    assert document.node_count == 2
    assert document.table_count == 1
    assert document.reference_count == 1
    assert document.image_dependent_count == 1


# --- resolution against the preserved bytes ------------------------------------------------------


def test_an_exact_quote_resolves_at_a_true_offset_into_the_preserved_bytes(
    fixtures_dir: Path,
) -> None:
    """EXACT means the quote is at that position in the bytes SEC published, not near it.

    The offset is what the review UI highlights, so it is checked by reading the preserved text
    back at the offset rather than by trusting the resolution label.
    """
    text = preserved(fixtures_dir, PRE_2001)
    quote = "The Company designs, manufactures and markets microprocessor-based personal"
    outcome = ArtifactIndex({PRE_2001[1]: text}).resolve(PRE_2001[1], quote, node_id="n1")
    assert outcome.resolution is Resolution.EXACT
    assert outcome.resolved is True
    assert outcome.offset is not None
    assert text[outcome.offset : outcome.offset + len(quote)] == quote


def test_a_quote_the_model_reflowed_resolves_whitespace_normalised(fixtures_dir: Path) -> None:
    """A filing wraps prose at column 74 with arbitrary internal spacing; a model does not.

    Recording a correctly copied sentence as invented because the line breaks moved would make the
    unresolved count a measure of typography. The quote below is genuinely absent from the raw
    bytes, which is asserted, so this cannot pass as an EXACT match in disguise.
    """
    text = preserved(fixtures_dir, PRE_2001)
    quote = (
        "The Company designs, manufactures and markets microprocessor-based personal computers "
        "and related personal computing products for sale primarily to business, education, "
        "home, and government customers."
    )
    assert quote not in text, "the reflowed quote must not be present verbatim"
    outcome = ArtifactIndex({PRE_2001[1]: text}).resolve(PRE_2001[1], quote, node_id="n1")
    assert outcome.resolution is Resolution.WHITESPACE_NORMALISED
    assert outcome.resolved is True


def test_a_quote_split_by_inline_xbrl_markup_resolves_text_only(fixtures_dir: Path) -> None:
    """In a real inline-XBRL filing a sentence a human calls verbatim is not contiguous at all.

    Here `Total net sales` and the figure `94,036` are separated by a closing span, two table
    cells, an opening span and an ix:nonFraction element carrying a us-gaap concept. Without the
    tag-stripped search every table citation in a modern filing would be recorded as fabricated.
    """
    text = preserved(fixtures_dir, INLINE_XBRL)
    quote = "Total net sales 94,036"
    assert quote not in text, "the quote must not be contiguous in the preserved markup"
    outcome = ArtifactIndex({INLINE_XBRL[1]: text}).resolve(INLINE_XBRL[1], quote, node_id="n1")
    assert outcome.resolution is Resolution.TEXT_ONLY
    assert outcome.resolved is True


def test_a_fabricated_quote_resolves_unresolved_against_a_real_filing(fixtures_dir: Path) -> None:
    """ANTI-VACUITY for all three searches above. They must not resolve everything handed to them.

    The sentence below is plausible English about the right issuer in the right decade and appears
    nowhere in the 240 KB submission. A search strategy that found it would make the citation rate
    a measure of nothing.
    """
    text = preserved(fixtures_dir, PRE_2001)
    outcome = ArtifactIndex({PRE_2001[1]: text}).resolve(
        PRE_2001[1],
        "The Company plans to open a chain of undersea theme parks during fiscal 1995.",
        node_id="n1",
    )
    assert outcome.resolution is Resolution.UNRESOLVED
    assert outcome.resolved is False
    assert outcome.offset is None
    assert outcome.occurrences == 0


def test_a_quote_at_the_ambiguity_threshold_still_locates_something() -> None:
    """MUTATION on the ambiguity guard: it must not fire at the threshold, only past it.

    A guard that flagged the boundary case would quietly discard legitimate citations to a phrase
    a filing happens to repeat, and the resolved count would drift down for reasons no reviewer
    could see.
    """
    quote = "the segment operating margin"
    text = " and ".join([quote] * AMBIGUITY_THRESHOLD)
    outcome = ArtifactIndex({"filing.htm": text}).resolve("filing.htm", quote, node_id="n1")
    assert outcome.resolution is Resolution.EXACT
    assert outcome.occurrences == AMBIGUITY_THRESHOLD
    assert outcome.offset == 0


def test_a_quote_past_the_ambiguity_threshold_carries_no_offset() -> None:
    """A reference pointing everywhere locates nothing, and must not be counted as resolved.

    Reporting the first of many occurrences would hand the review UI an arbitrary highlight and
    inflate the citation rate with references that support no particular passage.
    """
    quote = "the segment operating margin"
    text = " and ".join([quote] * (AMBIGUITY_THRESHOLD + 1))
    outcome = ArtifactIndex({"filing.htm": text}).resolve("filing.htm", quote, node_id="n1")
    assert outcome.resolution is Resolution.AMBIGUOUS
    assert outcome.occurrences == AMBIGUITY_THRESHOLD + 1
    assert outcome.offset is None
    assert outcome.resolved is False
    assert Resolution.AMBIGUOUS not in RESOLVED


@pytest.mark.parametrize("named", ["exhibit-99.htm", "a-file-nobody-submitted.htm"])
def test_a_quote_naming_the_wrong_file_resolves_against_the_file_that_holds_it(named: str) -> None:
    """A right sentence under a wrong filename is a LABELLING error, not a fabrication.

    The two deserve different verdicts, so the search continues across every submitted artifact
    and the outcome names the artifact that actually contains the quote — including when the
    filename the model wrote was never submitted at all.
    """
    index = ArtifactIndex(
        {
            "primary.htm": "Total net sales increased 2 percent during the quarter.",
            "exhibit-99.htm": "Certification pursuant to the applicable rule.",
        }
    )
    outcome = index.resolve(named, "Total net sales increased 2 percent", node_id="n1")
    assert outcome.resolved is True
    assert outcome.filename == "primary.htm", "the outcome names where the quote actually is"


def test_an_empty_quote_and_an_empty_submission_are_named_separately() -> None:
    """Two different failures that both mean `not located`, kept distinguishable in the record.

    A model that emitted a reference with no quote and a run that submitted no text at all are
    different problems with different fixes, and a single UNRESOLVED bucket would hide both.
    """
    populated = ArtifactIndex({"filing.htm": "Total net sales increased 2 percent."})
    assert populated.resolve("filing.htm", "   ", node_id="n1").resolution is Resolution.EMPTY_QUOTE
    empty = ArtifactIndex({})
    assert empty.filenames == ()
    outcome = empty.resolve("filing.htm", "Total net sales", node_id="n1")
    assert outcome.resolution is Resolution.NO_SUCH_ARTIFACT
    assert outcome.resolved is False


# --- numeric signals, arithmetic only ------------------------------------------------------------


def test_note_and_page_numbers_are_below_the_noise_floor() -> None:
    """A bare 3 occurs in every filing ever written; counting it makes the verbatim rate a lie.

    The floor is what stops `Note 3` and `page 12` from being scored as reported figures, and the
    large number in the same sentence proves the extractor is still extracting.
    """
    found = extract_numbers("As described in Note 3 on page 12, Item 7 reported 1,234,567 units.")
    assert found == ["1,234,567"]


def test_the_noise_floor_is_a_digit_count_and_a_four_digit_year_clears_it() -> None:
    """CHARACTERISATION of the floor as implemented: four digits, whatever they mean.

    Recorded because every rate this module reports is computed over whatever the floor admits, so
    a change to it silently rescales the verbatim rate for every model ever compared. It also
    records honestly that a year is NOT excluded despite the module comment naming years, which is
    a measurement question for a reviewer and not something a test should quietly bless.
    """
    assert extract_numbers("during fiscal 2024") == ["2024"]
    assert extract_numbers("during fiscal 998") == []


def test_thousands_separators_do_not_decide_whether_a_figure_was_reported() -> None:
    """A filing and a model may legitimately write one figure two ways, in either direction.

    Scoring 1,234,567 against 1234567 as a fabrication would make the signal measure formatting
    rather than fidelity, which is the opposite of what it is for.
    """
    assert (
        assess(
            reported_text="net sales of 1,234,567",
            tables=[],
            source_text="net sales of 1234567",
        ).numbers_verbatim_in_source
        == 1
    )
    assert (
        assess(
            reported_text="net sales of 1234567",
            tables=[],
            source_text="net sales of 1,234,567",
        ).numbers_verbatim_in_source
        == 1
    )


def test_a_figure_absent_from_the_source_is_not_counted_verbatim() -> None:
    """MUTATION. Separator-insensitive comparison must not degrade into matching everything.

    If it did, `numbers_verbatim_in_source` would equal `numbers_checked` for every response ever
    validated and the signal would be a constant.
    """
    signals = assess(
        reported_text="net sales of 9,999,999",
        tables=[],
        source_text="net sales of 1,234,567",
    )
    assert signals.numbers_checked == 1
    assert signals.numbers_verbatim_in_source == 0
    assert signals.verbatim_rate == 0.0


def test_currency_and_percentage_formatting_is_reported_as_preserved_or_not() -> None:
    """Formatting preservation is a separate, stricter signal than the bare-number comparison.

    The same figure counts as reported when the separators move and as UNPRESERVED when the
    currency marker is dropped, so a reviewer can see which of the two a model did.
    """
    preserved_signal = assess(
        reported_text="a charge of $98,765.43",
        tables=[],
        source_text="a charge of $98,765.43 was recorded",
    )
    assert preserved_signal.formatted_numbers_checked == 1
    assert preserved_signal.formatted_numbers_preserved == 1

    dropped = assess(
        reported_text="a charge of $98,765.43",
        tables=[],
        source_text="a charge of 98,765.43 was recorded",
    )
    assert dropped.formatted_numbers_checked == 1
    assert dropped.formatted_numbers_preserved == 0
    assert dropped.numbers_verbatim_in_source == 1, "the figure itself is still reported"


def test_a_column_holding_its_own_total_is_reported_coherent() -> None:
    """An ARITHMETIC OBSERVATION, and deliberately nothing more.

    The module does not read the row label, does not conclude the row is a total, and would report
    the same signal if the label said something else entirely. rules.md invariant 14: backend code
    does not decide what a number means.
    """
    signals = assess(
        reported_text="",
        tables=[{"rows": [["Americas", "40,315"], ["Europe", "24,930"], ["Total", "65,245"]]}],
        source_text="",
    )
    assert signals.tables_checked == 1
    assert signals.tables_with_a_coherent_column == 1


def test_a_column_of_unrelated_figures_is_not_reported_coherent() -> None:
    """MUTATION. A coherence check that fires on any three numbers is not a check.

    It is also the reason an incoherent table is not reported as WRONG: plenty of legitimate
    tables carry no total row, and this signal only distinguishes models on the same filing.
    """
    signals = assess(
        reported_text="",
        tables=[{"rows": [["Americas", "40,315"], ["Europe", "24,930"], ["Japan", "6,101"]]}],
        source_text="",
    )
    assert signals.tables_checked == 1
    assert signals.tables_with_a_coherent_column == 0


def test_two_rows_are_never_enough_to_call_a_column_coherent() -> None:
    """With two rows, `one value equals the sum of the others` degenerates into `they are equal`.

    A repeated figure — the same number in two periods — is not a total, and without the minimum
    row count every such table would be scored as carrying one.
    """
    signals = assess(
        reported_text="",
        tables=[{"rows": [["Americas", "40,315"], ["Europe", "40,315"]]}],
        source_text="",
    )
    assert signals.tables_checked == 1
    assert signals.tables_with_a_coherent_column == 0


# --- the verdict ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # Prose instead of a document, invalid YAML, and good YAML inside a Markdown fence, which
        # is the failure a chat-tuned model produces most readily and which stops the parse dead.
        "the filing was too long for me to parse in one pass",
        "nodes: [unclosed\n",
        "```\nnodes:\n  - id: n1\n```\n",
    ],
)
def test_an_unparseable_response_is_returned_as_a_result_never_raised(text: str) -> None:
    """A failure here is a RESULT, not an exception. The response was bought and is preserved.

    It still produces a validation record, still reaches the review UI, and still shows its exact
    bytes so a person can decide whether the prompt or the model is at fault.
    """
    result, document = validate_response(text, artifact_texts=ONE_ARTIFACT)
    assert result.status is ValidationStatus.UNPARSEABLE
    assert document is None
    assert result.yaml_parsed is False
    assert result.findings, "an unparseable response must say why"
    assert result.response_characters == len(text)
    assert result.source_characters == len(ONE_ARTIFACT["filing.htm"])


def test_an_empty_response_is_reported_empty_with_every_artifact_uncited() -> None:
    """A model that returned nothing has covered nothing, and the record has to say so.

    EMPTY is kept separate from UNPARSEABLE because they are different failures: one produced no
    text at all, the other produced text that is not a document.
    """
    result, document = validate_response("   \n  ", artifact_texts=ONE_ARTIFACT)
    assert result.status is ValidationStatus.EMPTY
    assert document is None
    assert result.response_characters == 0
    assert result.artifacts_submitted == 1
    assert result.artifacts_referenced == 0
    assert result.artifacts_unreferenced == ("filing.htm",)
    assert result.numeric["numbers_checked"] == 0


def test_a_reference_that_does_not_land_makes_the_verdict_partial() -> None:
    """A citation that cannot be found in the preserved bytes is the loudest signal available.

    It must never be absorbed into a clean verdict, and the finding names how many failed so the
    number is visible without opening the reference list.
    """
    nodes = block(
        """
        - id: n1
          title: Net sales
          source:
            - filename: filing.htm
              quote: Total net sales fell by half during the quarter
        """
    )
    result, document = validate_response(response(nodes=nodes), artifact_texts=ONE_ARTIFACT)
    assert result.status is ValidationStatus.PARTIAL
    assert document is not None
    assert result.references_unresolved == 1
    assert result.references_resolved == 0
    assert result.resolution_breakdown == {Resolution.UNRESOLVED.value: 1}
    assert any("could not be located in the preserved bytes" in f for f in result.findings)


def test_a_model_declared_unresolved_item_makes_the_verdict_partial() -> None:
    """Uncertainty the model itself declared is carried straight through to the verdict.

    The complete-content invariant says uncertainty produces PARTIAL, never a false complete. A
    validator that ignored a declaration because every reference happened to resolve would be
    overruling the only party that read the filing.
    """
    result, _ = validate_response(
        response(
            nodes=CITING_NODE,
            unresolved=block(
                """
                - reason: a scanned exhibit could not be read
                """
            ),
        ),
        artifact_texts=ONE_ARTIFACT,
    )
    assert result.status is ValidationStatus.PARTIAL
    assert result.declared_unresolved == 1
    assert result.references_unresolved == 0, "the declaration alone is enough"
    assert any("declared 1 unresolved item" in f for f in result.findings)


def test_a_submitted_artifact_with_no_resolved_citation_makes_the_verdict_partial() -> None:
    """Every artifact that was sent has to be represented, and the unnamed one is named.

    A parse that cited the primary document beautifully and never once mentioned the exhibit that
    was sent alongside it has not covered the submission, however good the citations it does have.
    """
    result, _ = validate_response(
        response(nodes=CITING_NODE),
        artifact_texts={
            **ONE_ARTIFACT,
            "exhibit-99.htm": "Certification pursuant to the applicable rule.",
        },
    )
    assert result.status is ValidationStatus.PARTIAL
    assert result.artifacts_submitted == 2
    assert result.artifacts_referenced == 1
    assert result.artifacts_unreferenced == ("exhibit-99.htm",)
    assert any("exhibit-99.htm" in f for f in result.findings)


def test_an_unanalysed_image_member_is_reported_and_never_silently_claimed() -> None:
    """A run without the image stage does not get to claim image coverage.

    Only the parsing model is required, so a parser-only run is complete and valid — but it must
    say which members it did not look at rather than counting them as covered.
    """
    result, _ = validate_response(
        response(nodes=CITING_NODE),
        artifact_texts=ONE_ARTIFACT,
        image_filenames=("exhibit-graphic.jpg",),
        images_analysed=False,
    )
    assert result.status is ValidationStatus.PARTIAL
    assert result.artifacts_submitted == 2
    assert any("does not claim image coverage" in f for f in result.findings)


def test_an_analysed_image_member_raises_no_finding() -> None:
    """MUTATION on the image guard: it reports an image that was SKIPPED, not one that was read.

    Without this, the guard could be flagging the mere presence of an image and the run would be
    PARTIAL forever no matter which stages were selected.
    """
    result, _ = validate_response(
        response(nodes=CITING_NODE),
        artifact_texts=ONE_ARTIFACT,
        image_filenames=("exhibit-graphic.jpg",),
        images_analysed=True,
    )
    assert result.status is ValidationStatus.REVIEW_REQUIRED
    assert result.findings == ()


def test_a_clean_response_reaches_review_required_and_goes_no_further() -> None:
    """THE CEILING. Every signal is good and the verdict is still `a person must look at this`.

    What was measured is that the citations resolve and every submitted artifact is represented.
    The complete-content invariant asks whether every human-readable source RANGE is represented,
    which none of these signals answers, so rounding them up to a completeness claim would be
    exactly the false complete the invariant exists to forbid.
    """
    result, document = validate_response(response(nodes=CITING_NODE), artifact_texts=ONE_ARTIFACT)
    assert result.status is ValidationStatus.REVIEW_REQUIRED
    assert result.findings == ()
    assert result.boundary_ok is True
    assert result.boundary_violations == ()
    assert result.missing_envelope_keys == ()
    assert result.reference_count == 1
    assert result.references_resolved == 1
    assert result.artifacts_unreferenced == ()
    assert document is not None
    assert result.status.value != "COMPLETE"


def test_markup_inside_a_yaml_scalar_is_not_a_boundary_violation() -> None:
    """CORRECTED. A verbatim quote from an SGML or inline-XBRL filing contains that filing's tags.

    This test used to assert the OPPOSITE, and the assertion was the defect. The textual detectors
    cannot tell markup that IS the serialization from the same characters inside a YAML string, and
    a parser response is REQUIRED to quote filings verbatim — so under the old rule no response
    quoting a pre-2001 filing could ever pass, which is the entire corpus era this product exists
    to cover. Measured on the first real benchmark: a model returned a well-formed YAML document
    whose source quotes carried the filing's own tags and it was rejected for `html_markup`.

    A document that PARSES as one YAML 1.2 mapping is one unfenced YAML document; only
    serialization violations still apply to it.
    """
    nodes = block(
        """
        - id: n1
          title: Net sales
          content: Total net sales increased 2 percent
          source:
            - filename: filing.htm
              quote: "<span>Total net sales</span> increased 2 percent"
        """
    )
    result, document = validate_response(response(nodes=nodes), artifact_texts=ONE_ARTIFACT)
    assert result.boundary_ok is True, (
        f"a quoted scalar containing markup was refused: {result.boundary_violations}"
    )
    assert document is not None
    assert result.yaml_parsed is True


def test_a_response_that_is_really_markup_is_still_refused() -> None:
    """MUTATION PROOF for the test above: the relaxation is scoped to scalars, not to responses.

    Without this, the previous test would pass just as happily over a validator that had stopped
    checking markup entirely — which is what a reader should suspect a change like that of doing.
    """
    result, document = validate_response(
        "<html><body>this is not a parse</body></html>", artifact_texts=ONE_ARTIFACT
    )
    assert result.boundary_ok is False
    assert "html_markup" in result.boundary_violations
    assert document is None, "markup must not be read as a parsed artifact"


def test_a_json_response_is_still_refused_even_though_json_parses_as_yaml() -> None:
    """JSON is a YAML subset, so "it parses as YAML" can never be the whole test.

    ADR-0013 prohibits JSON in both directions. A provider returning JSON parses cleanly as a YAML
    mapping, so the JSON detectors are exactly the ones that must survive the scalar exemption.
    """
    result, _ = validate_response(
        '{"artifact": {"schema_version": "parser-response-v1"}, "nodes": []}',
        artifact_texts=ONE_ARTIFACT,
    )
    assert result.boundary_ok is False
    assert "json_object" in result.boundary_violations


def test_the_manifest_carries_every_reference_outcome_and_the_status_note() -> None:
    """The exported record is what an auditor reads, so the disclaimer travels with the numbers.

    A coverage figure printed without the sentence explaining what it cannot establish is a
    completeness claim by omission.
    """
    result, _ = validate_response(response(nodes=CITING_NODE), artifact_texts=ONE_ARTIFACT)
    mapping = result.to_mapping()
    assert mapping["status"] == "REVIEW_REQUIRED"
    assert "COMPLETE is not a value this validator can issue" in mapping["status_note"]
    assert len(mapping["references"]) == 1
    assert mapping["references"][0]["node_id"] == "n1"
    assert mapping["references"][0]["resolution"] == Resolution.EXACT.value


# --- COMPLETE is not available, and is not reachable ---------------------------------------------


def test_the_status_enum_has_no_complete_member() -> None:
    """A status value that exists is a status value something will eventually set.

    Absence is the control. Anything weaker — a COMPLETE member nothing currently assigns — is one
    optimistic patch away from a false complete reaching a reviewer as a finished verdict.
    """
    assert {status.name for status in ValidationStatus} == {
        "REVIEW_REQUIRED",
        "PARTIAL",
        "UNPARSEABLE",
        "EMPTY",
    }
    assert getattr(ValidationStatus, "COMPLETE", None) is None
    with pytest.raises(ValueError, match="COMPLETE"):
        ValidationStatus("COMPLETE")


def test_no_code_path_in_the_package_can_name_a_complete_verdict() -> None:
    """MUTATION at the source level: the enum could be dodged by constructing the value.

    Every `ValidationStatus.X` reference in the package is collected from the syntax tree and
    checked against the four permitted names, and no string literal anywhere in the package is
    exactly `COMPLETE`, which is the other way the value could be reached.
    """
    permitted = {"REVIEW_REQUIRED", "PARTIAL", "UNPARSEABLE", "EMPTY"}
    referenced: set[str] = set()
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "ValidationStatus"
            ):
                referenced.add(node.attr)
            if isinstance(node, ast.Constant) and node.value == "COMPLETE":
                raise AssertionError(f"{path.name} names the literal COMPLETE")
    assert referenced, "the scan found no status references at all, so it proves nothing"
    assert referenced <= permitted, f"a status outside the permitted set: {referenced - permitted}"


@pytest.mark.parametrize(
    ("text", "artifacts"),
    [
        ("", {}),
        ("   ", {"filing.htm": "Total net sales increased 2 percent."}),
        ("not a document at all", {"filing.htm": "Total net sales increased 2 percent."}),
        ("nodes:\n", {"filing.htm": "Total net sales increased 2 percent."}),
        (response(nodes=CITING_NODE), ONE_ARTIFACT),
        (response(nodes=CITING_NODE), {}),
    ],
)
def test_no_response_at_all_produces_a_verdict_stronger_than_review_required(
    text: str, artifacts: dict[str, str]
) -> None:
    """The ceiling holds across every shape of response the validator has been given.

    Including the degenerate ones: no artifacts submitted, an envelope with no nodes, and a
    perfect parse. REVIEW_REQUIRED is the strongest verdict any of them reaches.
    """
    result, _ = validate_response(text, artifact_texts=artifacts)
    assert result.status in {
        ValidationStatus.REVIEW_REQUIRED,
        ValidationStatus.PARTIAL,
        ValidationStatus.UNPARSEABLE,
        ValidationStatus.EMPTY,
    }
    assert result.to_mapping()["status"] != "COMPLETE"
