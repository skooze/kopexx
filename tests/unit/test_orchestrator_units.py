"""The orchestrator's arithmetic and its refusals: output sizing, the durable ceiling, the catalog.

HERMETIC. Every test here builds its own inputs — a synthetic corpus manifest and a spend journal,
both under pytest's `tmp_path`. Nothing reaches a provider, nothing reads a credential, nothing
opens a socket, and nothing depends on the committed corpus manifest staying the shape it has today.

WHAT IS ACTUALLY BEING TESTED. Not that these functions return numbers; that is arithmetic. The
subjects are the three things this package has to get right BEFORE any money is spent:

    an output budget that leaves room for a model's reasoning as well as its answer, and that never
    exceeds a verified output limit or the context the input has left;

    a cumulative ceiling that OUTLIVES the process that spent against it — a ceiling that resets on
    restart is a per-process suggestion, and a reservation that is released when the request fails
    would let a run of billable rejections walk straight past it;

    a catalog that never offers an issuer, a ticker or a filing the preserved corpus does not
    actually hold. rules.md forbids fabricated identity, and 68 of the 112 corpus issuers have no
    current ticker at all.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from packages.model_catalog import CostCeilingExceededError, ModelRole, PriceInputs
from packages.orchestrator import (
    MINIMUM_PARSE_OUTPUT_TOKENS,
    OUTPUT_RATIO_OF_INPUT,
    CorpusFilingCatalog,
    NoParsingModelError,
    RunRequest,
    SpendJournal,
    sized_output_tokens,
)
from packages.storage import FilesystemObjectStore

AT = "2026-08-03T00:00:00+00:00"


# --- the output sizing policy -------------------------------------------------------------------


def test_the_sizing_constants_are_a_stated_policy_not_a_habit() -> None:
    """Anti-vacuity. Every sizing test below is meaningless if the floor or the ratio is degenerate.

    A zero floor would make the reasoning-room guarantee vacuous, and a ratio of zero or above one
    would make "scales with the input" either constant or larger than the filing itself.
    """
    assert MINIMUM_PARSE_OUTPUT_TOKENS > 0, "a zero floor guarantees a model no room at all"
    assert 0 < OUTPUT_RATIO_OF_INPUT <= 1


def test_a_tiny_input_still_gets_the_documented_output_floor() -> None:
    """A model that emits reasoning before its answer needs room for BOTH, whatever the input size.

    Phase 1 measured a candidate whose entire 8-token output budget went to a reasoning block,
    leaving an empty answer with stop reason `max_tokens` — a well-formed response with nothing in
    it. Sizing the budget from the visible answer alone reproduces that at any scale, so a ten-token
    input gets the floor rather than six tokens.
    """
    assert (
        sized_output_tokens(estimated_input_tokens=10, model_max_output=64000, model_context=200000)
        == MINIMUM_PARSE_OUTPUT_TOKENS
    )


def test_the_request_never_exceeds_the_models_verified_output_limit() -> None:
    """A budget above the verified limit is a request the provider rejects, billed or not.

    The limit is evidence from the reviewed capability snapshot. Asking past it is the same class of
    error as inventing a region: a number the product wished were true.
    """
    sized = sized_output_tokens(
        estimated_input_tokens=500_000, model_max_output=4096, model_context=1_000_000
    )
    assert sized == 4096


def test_the_request_never_exceeds_what_the_context_has_left_after_the_input() -> None:
    """Input plus output must fit one context window, or the answer is truncated mid-artifact.

    A truncated parse is the failure INTACT_SOURCE_ONLY exists to prevent, and it is worse than a
    refusal because it looks like a complete answer.
    """
    sized = sized_output_tokens(
        estimated_input_tokens=98_000, model_max_output=64_000, model_context=100_000
    )
    assert sized == 2_000
    assert 98_000 + sized <= 100_000


def test_between_the_floor_and_the_caps_the_budget_scales_with_the_input() -> None:
    """A larger filing gets a larger budget, so the floor is a floor and not the whole policy.

    MUTATION GUARD: an implementation that simply returned MINIMUM_PARSE_OUTPUT_TOKENS would pass
    the floor test above and fail here.
    """
    sized = sized_output_tokens(
        estimated_input_tokens=100_000, model_max_output=64_000, model_context=400_000
    )
    assert sized == 60_000
    assert sized > MINIMUM_PARSE_OUTPUT_TOKENS


def test_the_ratio_rounds_up_so_a_fraction_of_a_token_is_never_dropped() -> None:
    """Rounding a budget DOWN spends money to receive one token less than the policy asked for.

    The direction is chosen deliberately: the caps below are the real protection against asking for
    too much, so the ratio may round up without any risk of exceeding a verified limit.
    """
    estimated = 20_001
    expected = int(math.ceil(estimated * OUTPUT_RATIO_OF_INPUT))
    sized = sized_output_tokens(
        estimated_input_tokens=estimated, model_max_output=64_000, model_context=400_000
    )
    assert sized == expected
    assert sized == 12_001


def test_a_growing_input_never_asks_for_a_smaller_budget_while_the_context_is_ample() -> None:
    """The policy is monotonic where it is meant to be: more source, never less room to answer.

    Checked only where the context is ample, because the context cap legitimately shrinks the budget
    once the input approaches the window — that behaviour has its own test above.
    """
    budgets = [
        sized_output_tokens(
            estimated_input_tokens=size, model_max_output=1_000_000, model_context=100_000_000
        )
        for size in (0, 1_000, 13_333, 50_000, 250_000)
    ]
    assert budgets == sorted(budgets)
    assert budgets[0] < budgets[-1], "the sequence must actually grow, or monotonicity is vacuous"


def test_a_verified_output_limit_below_the_floor_wins_over_the_floor() -> None:
    """The floor is a preference; a verified limit is evidence, and evidence wins.

    This records real behaviour rather than the ideal: a model whose snapshot output limit is below
    MINIMUM_PARSE_OUTPUT_TOKENS is sized to its limit, not to the floor. Nothing else is possible —
    the alternative is a request the provider refuses — but it does mean the floor's reasoning-room
    guarantee cannot be honoured for such a model, which is a selection decision rather than a
    sizing one.
    """
    sized = sized_output_tokens(
        estimated_input_tokens=10, model_max_output=2_000, model_context=200_000
    )
    assert sized == 2_000
    assert sized < MINIMUM_PARSE_OUTPUT_TOKENS


def test_a_source_set_larger_than_the_context_never_produces_a_zero_or_negative_budget() -> None:
    """A non-positive `max_output_tokens` is a malformed provider request, not a small one.

    A filing whose estimated input already exceeds the window is refused as INCOMPATIBLE at
    preflight and is never invoked, so the clamp here is a last line rather than the decision — but
    it must still be a number a request could legally carry.
    """
    sized = sized_output_tokens(
        estimated_input_tokens=300_000, model_max_output=64_000, model_context=128_000
    )
    assert sized >= 1


# --- the run request ----------------------------------------------------------------------------


def test_a_run_without_a_parsing_model_is_refused_by_name() -> None:
    """ONLY THE PARSING MODEL IS REQUIRED, and a required role is never filled by inference.

    rules.md section 21 rule 8. The refusal is a typed error carrying the sentence a user reads,
    because the tempting repair — borrow the model some other selector holds — is exactly the silent
    substitution the product forbids.
    """
    with pytest.raises(NoParsingModelError) as error:
        RunRequest(cik="0000000101", parsing_label="").selection()
    message = str(error.value)
    assert "parsing model" in message
    assert "blank" in message


def test_a_whitespace_only_parsing_label_is_refused_too() -> None:
    """A label of spaces is not a model, and must not become one.

    The refusal currently arrives as the ValueError `RoleSelection` raises rather than as
    `NoParsingModelError`, because the request object tests the label for emptiness without
    stripping it. Both are accepted here so the invariant — no run without a real parsing model — is
    protected without freezing the less useful of the two error types.
    """
    with pytest.raises((NoParsingModelError, ValueError)):
        RunRequest(cik="0000000101", parsing_label="   ").selection()


def test_three_blank_optional_roles_are_a_valid_complete_configuration() -> None:
    """A parser-only run is a COMPLETE run, not a partially configured one.

    The image, summary and analysis selectors may be left blank, and a blank one runs NO stage. The
    selection carries `None` for each rather than omitting it, so "the user chose nothing" is a
    value a reviewer can see in the record.
    """
    selection = RunRequest(cik="0000000101", parsing_label="Model One").selection()
    assert selection.parsing == "Model One"
    assert selection.image is None
    assert selection.summary is None
    assert selection.analysis is None
    assert selection.selected_roles == (ModelRole.PARSING,)


def test_a_blank_string_selector_becomes_a_blank_role_rather_than_a_label() -> None:
    """The UI's explicit `None — skip this stage` option submits an empty string, not a null.

    An empty string carried through as a label would reach the catalog and fail as an unknown model,
    which reports the wrong problem to the wrong person.
    """
    selection = RunRequest(
        cik="0000000101",
        parsing_label="Model One",
        image_label="",
        summary_label="",
        analysis_label="",
    ).selection()
    assert (selection.image, selection.summary, selection.analysis) == (None, None, None)
    assert selection.selected_roles == (ModelRole.PARSING,)


def test_a_filled_optional_selector_does_add_its_role() -> None:
    """MUTATION GUARD for the two tests above: the opposite case is NOT blanked.

    An implementation that discarded every optional selector would pass both blank-role tests and
    fail here, and a run that silently dropped a stage the user asked for is the same defect class
    as one that silently adds one.
    """
    selection = RunRequest(
        cik="0000000101", parsing_label="Model One", summary_label="Model Two"
    ).selection()
    assert selection.summary == "Model Two"
    assert selection.selected_roles == (ModelRole.PARSING, ModelRole.SUMMARY)
    assert selection.label_for(ModelRole.IMAGE) is None
    assert selection.label_for(ModelRole.SUMMARY) == "Model Two"


def test_the_parsing_model_is_never_borrowed_to_fill_a_blank_role() -> None:
    """No role inherits another's model — rules.md section 21 rule 8, stated as an assertion.

    The failure this blocks is silent and expensive: three extra stages running on a model nobody
    selected for them, each one billable.
    """
    selection = RunRequest(cik="0000000101", parsing_label="Model One").selection()
    for role in (ModelRole.IMAGE, ModelRole.SUMMARY, ModelRole.ANALYSIS):
        assert selection.label_for(role) is None
        assert selection.label_for(role) != selection.parsing


# --- the durable spend journal --------------------------------------------------------------------


def price(input_per_1k: str = "0.001", output_per_1k: str = "0.004") -> PriceInputs:
    """Synthetic price inputs. Not any real model's price, and never read from a snapshot here."""
    return PriceInputs(
        input_per_1k=Decimal(input_per_1k),
        output_per_1k=Decimal(output_per_1k),
        currency="USD",
        source="a synthetic test price",
        effective_date="2026-01-01",
    )


def journal(root: Path, *, ceiling_usd: str = "1.00") -> SpendJournal:
    """A journal over a real directory, so the durability tests exercise the real read path."""
    return SpendJournal(FilesystemObjectStore(root / "spend"), ceiling_usd=ceiling_usd)


def test_a_bound_is_the_worst_case_and_spends_nothing(tmp_path: Path) -> None:
    """A number shown to a user before they authorize must not itself consume the ceiling."""
    book = journal(tmp_path)
    bound = book.bound(price(), max_input_tokens=1000, max_output_tokens=1000)
    assert bound == Decimal("0.005")
    assert book.spent_usd == Decimal(0)
    assert book.entries == ()


def test_authorize_reserves_the_worst_case_before_the_call(tmp_path: Path) -> None:
    """Reserve before, settle after. The reservation is the bound, not a guess at the outcome.

    rules.md section 21 rule 11: cost is previewed and authorized BEFORE the invocation, never
    reconciled after it.
    """
    book = journal(tmp_path)
    reserved = book.authorize(
        price(),
        max_input_tokens=1000,
        max_output_tokens=1000,
        at=AT,
        run_id="run-1",
        job_id="job-1",
        model_label="Model One",
    )
    assert reserved == Decimal("0.005")
    assert book.spent_usd == reserved
    assert book.remaining_usd == Decimal("1.00") - reserved
    assert [e.kind for e in book.entries] == ["RESERVATION"]
    assert book.entries[0].released_usd == Decimal(0)


def test_an_invocation_past_the_cumulative_ceiling_is_refused_with_the_three_numbers(
    tmp_path: Path,
) -> None:
    """The refusal has to be actionable, so it names the ceiling, the spend and the estimate.

    "Refused" on its own sends a user to a support channel; the three numbers let them see that the
    remaining budget is smaller than this one filing, which is a decision they can make.
    """
    book = journal(tmp_path, ceiling_usd="0.004")
    with pytest.raises(CostCeilingExceededError) as error:
        book.authorize(
            price(),
            max_input_tokens=1000,
            max_output_tokens=1000,
            at=AT,
            run_id="run-1",
            job_id="job-1",
            model_label="Model One",
        )
    assert error.value.ceiling_usd == "0.004"
    assert error.value.spent_usd == "0"
    assert error.value.estimate_usd == "0.005"
    assert "shrunk, dropped or downgraded" in str(error.value)
    assert book.spent_usd == Decimal(0), "a refused invocation must not charge anything"
    assert book.entries == (), "a refused invocation must not enter the journal"


def test_a_bound_that_fits_is_not_refused(tmp_path: Path) -> None:
    """MUTATION GUARD: the OPPOSITE case is not flagged.

    A ceiling that refused everything would pass the refusal test above while making the product
    incapable of spending a cent. The boundary is inclusive — a bound that exactly consumes the
    remaining budget is authorized, because `spent + estimate > ceiling` is the refusal condition.
    """
    book = journal(tmp_path, ceiling_usd="0.005")
    reserved = book.authorize(
        price(),
        max_input_tokens=1000,
        max_output_tokens=1000,
        at=AT,
        run_id="run-1",
        job_id="job-1",
        model_label="Model One",
    )
    assert reserved == Decimal("0.005")
    assert book.remaining_usd == Decimal(0)


def test_the_cumulative_ceiling_holds_across_a_sequence_of_filings(tmp_path: Path) -> None:
    """One parent run is many billable units, and the ceiling bounds the TOTAL, not each one.

    A five-year request is five independent invocations; a per-invocation check would authorize
    every one of them and spend five times the ceiling.
    """
    book = journal(tmp_path, ceiling_usd="0.010")
    for index in range(2):
        book.authorize(
            price(),
            max_input_tokens=1000,
            max_output_tokens=1000,
            at=AT,
            run_id="run-1",
            job_id=f"job-{index}",
            model_label="Model One",
        )
    assert book.remaining_usd == Decimal("0.000")
    with pytest.raises(CostCeilingExceededError):
        book.authorize(
            price(),
            max_input_tokens=1,
            max_output_tokens=1,
            at=AT,
            run_id="run-1",
            job_id="job-2",
            model_label="Model One",
        )


def test_settle_replaces_the_reservation_with_the_measured_amount(tmp_path: Path) -> None:
    """The worst case is released and the measured cost charged, with BOTH halves recorded.

    An append-only journal that overwrote the reservation would make the arithmetic unauditable: a
    reviewer could no longer see what was reserved, only what was eventually claimed.
    """
    book = journal(tmp_path)
    reserved = book.authorize(
        price(),
        max_input_tokens=1000,
        max_output_tokens=1000,
        at=AT,
        run_id="run-1",
        job_id="job-1",
        model_label="Model One",
    )
    actual = book.settle(
        price(),
        reserved=reserved,
        input_tokens=10,
        output_tokens=2,
        at=AT,
        run_id="run-1",
        job_id="job-1",
        model_label="Model One",
    )
    assert actual == Decimal("0.000018")
    assert actual < reserved
    assert book.spent_usd == actual, "the reservation must no longer be charged as well"
    assert [e.kind for e in book.entries] == ["RESERVATION", "SETTLEMENT"]
    settlement = book.entries[1]
    assert settlement.amount_usd == actual
    assert settlement.released_usd == reserved
    assert "measured 10 input and 2 output tokens" in settlement.note


def test_a_failed_billable_attempt_keeps_its_reservation_charged(tmp_path: Path) -> None:
    """A request that failed still cost money, so its reservation stays charged until settled.

    A ledger that released on failure would let a run of billable rejections walk straight past the
    ceiling — which is the expensive half of "reserve before, settle after".
    """
    book = journal(tmp_path, ceiling_usd="0.009")
    reserved = book.authorize(
        price(),
        max_input_tokens=1000,
        max_output_tokens=1000,
        at=AT,
        run_id="run-1",
        job_id="job-1",
        model_label="Model One",
    )
    # The provider rejected this attempt: nothing is settled, and nothing is given back.
    assert book.spent_usd == reserved
    with pytest.raises(CostCeilingExceededError):
        book.authorize(
            price(),
            max_input_tokens=1000,
            max_output_tokens=1000,
            at=AT,
            run_id="run-1",
            job_id="job-2",
            model_label="Model One",
        )
    assert journal(tmp_path, ceiling_usd="0.009").spent_usd == reserved


def test_a_new_journal_over_the_same_directory_sees_the_previous_spend(tmp_path: Path) -> None:
    """THE WHOLE POINT. A ceiling that resets when the process does is not a ceiling.

    `SpendLedger` bounds one invocation in memory, which is correct and insufficient: the authorized
    Phase 2 ceiling is CUMULATIVE, so the total has to outlive the process that spent it. This is
    the same directory read by a journal that never saw the first one.
    """
    first = journal(tmp_path, ceiling_usd="0.006")
    reserved = first.authorize(
        price(),
        max_input_tokens=1000,
        max_output_tokens=1000,
        at=AT,
        run_id="run-1",
        job_id="job-1",
        model_label="Model One",
    )

    restarted = journal(tmp_path, ceiling_usd="0.006")
    assert restarted.spent_usd == reserved
    assert restarted.remaining_usd == Decimal("0.001")
    assert [e.kind for e in restarted.entries] == ["RESERVATION"]
    assert restarted.entries[0].run_id == "run-1"
    assert restarted.entries[0].job_id == "job-1"
    assert restarted.entries[0].model_label == "Model One"
    with pytest.raises(CostCeilingExceededError):
        restarted.authorize(
            price(),
            max_input_tokens=1000,
            max_output_tokens=1000,
            at=AT,
            run_id="run-2",
            job_id="job-2",
            model_label="Model One",
        )


def test_a_fresh_directory_starts_at_zero(tmp_path: Path) -> None:
    """MUTATION GUARD for durability: spend is read from the journal, not carried in a global.

    If the restart test above passed because the total lived somewhere process-wide, this one would
    fail — a brand-new directory would report the other journal's spend.
    """
    spent = journal(tmp_path / "one", ceiling_usd="1.00")
    spent.authorize(
        price(),
        max_input_tokens=1000,
        max_output_tokens=1000,
        at=AT,
        run_id="run-1",
        job_id="job-1",
        model_label="Model One",
    )
    assert journal(tmp_path / "two", ceiling_usd="1.00").spent_usd == Decimal(0)


def test_money_is_decimal_end_to_end_and_a_six_decimal_price_multiplies_exactly(
    tmp_path: Path,
) -> None:
    """Money is Decimal, never float, through the journal and through its durable round trip.

    Binary floating point cannot represent these prices: 3 * 0.000123 + 5 * 0.000456 evaluates to
    0.00264899999999999987906895704270482383435592055320739746..., and over a corpus of 613 filings
    that difference stops being invisible. The value that survives a restart must be the exact one.
    """
    book = journal(tmp_path)
    exact = price(input_per_1k="0.000123", output_per_1k="0.000456")
    reserved = book.authorize(
        exact,
        max_input_tokens=3000,
        max_output_tokens=5000,
        at=AT,
        run_id="run-1",
        job_id="job-1",
        model_label="Model One",
    )
    assert isinstance(reserved, Decimal)
    assert reserved == Decimal("0.002649")
    assert str(reserved) == "0.002649"
    assert Decimal(3 * 0.000123 + 5 * 0.000456) != reserved, "float would not have been exact"
    assert isinstance(book.spent_usd, Decimal)
    assert isinstance(book.remaining_usd, Decimal)

    restarted = journal(tmp_path)
    assert restarted.spent_usd == Decimal("0.002649")
    assert isinstance(restarted.entries[0].amount_usd, Decimal)


def test_a_zero_or_negative_ceiling_is_rejected(tmp_path: Path) -> None:
    """A ceiling of zero authorizes nothing and would read as "unlimited" to a careless caller.

    The refusal names the alternative: configure zero invocations, not a zero budget.
    """
    for index, value in enumerate(("0", "-1")):
        with pytest.raises(ValueError, match="positive"):
            journal(tmp_path / str(index), ceiling_usd=value)


# --- the corpus filing catalog --------------------------------------------------------------------

ZENITH = "0000000101"
NOVA = "0000000202"
HALCYON_FORMER = "Halcyon Paper Company"


def filing_row(
    *,
    cik: str,
    accession: str,
    filing_date: str,
    form_as_filed: str = "10-K",
    issuer_name_current: str,
    tickers_current: tuple[str, ...] = (),
    former_names: tuple[str, ...] = (),
    **extra: Any,
) -> dict[str, Any]:
    """One synthetic manifest row. Every field the catalog reads, none of them a real issuer."""
    row: dict[str, Any] = {
        "cik": cik,
        "accession": accession,
        "form_as_filed": form_as_filed,
        "filing_date": filing_date,
        "report_period": extra.get("report_period", filing_date),
        "issuer_name_current": issuer_name_current,
        "tickers_current": list(tickers_current),
        "former_names": [{"name": name} for name in former_names],
        "sic_description": extra.get("sic_description", "Synthetic Manufacturing"),
        "transport_era": extra.get("transport_era", "inline_xbrl"),
        "is_amendment": extra.get("is_amendment", False),
        "is_annual": form_as_filed.startswith("10-K"),
        "form_variant": extra.get("form_variant", form_as_filed),
        "package_file_count": extra.get("package_file_count", 2),
        "package_image_count": extra.get("package_image_count", 0),
        "primary_est_tokens_at_3_0": extra.get("primary_est_tokens_at_3_0", 120_000),
        "files": [
            {
                "filename": "primary.htm",
                "sha256": "0" * 64,
                "raw_bytes": 4096,
                "source_url": "https://example.invalid/primary.htm",
                "local_path": "corpus/primary.htm",
            }
        ],
    }
    return row


ZENITH_ROWS = [
    filing_row(
        cik=ZENITH,
        accession="0000000101-24-000001",
        filing_date="2024-11-15",
        issuer_name_current="Zenith Holdings Inc",
        tickers_current=("NOVA",),
        former_names=("Zenith Mining Corp",),
    ),
    filing_row(
        cik=ZENITH,
        accession="0000000101-22-000001",
        filing_date="2022-05-10",
        form_as_filed="10-Q",
        issuer_name_current="Zenith Holdings Inc",
        tickers_current=("NOVA",),
        former_names=("Zenith Mining Corp",),
    ),
    filing_row(
        cik=ZENITH,
        accession="0000000101-19-000001",
        filing_date="2019-02-01",
        issuer_name_current="Zenith Holdings Inc",
        tickers_current=("NOVA",),
        former_names=("Zenith Mining Corp",),
    ),
]

NOVA_ROWS = [
    filing_row(
        cik=NOVA,
        accession="0000000202-21-000001",
        filing_date="2021-07-07",
        issuer_name_current="Nova Industries Inc",
        former_names=(HALCYON_FORMER,),
    )
]


def manifest(tmp_path: Path, rows: list[dict[str, Any]], *, name: str = "corpus.json") -> Path:
    """Write a synthetic corpus manifest and return its path. No default path exists in the code."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def catalog(tmp_path: Path, rows: list[dict[str, Any]] | None = None) -> CorpusFilingCatalog:
    return CorpusFilingCatalog.from_manifest(
        manifest(tmp_path, ZENITH_ROWS + NOVA_ROWS if rows is None else rows)
    )


def test_the_synthetic_manifest_indexes_both_issuers_and_every_filing(tmp_path: Path) -> None:
    """Anti-vacuity. Every catalog test below is meaningless if the manifest did not load."""
    found = catalog(tmp_path)
    assert found.entity_count == 2
    assert found.filing_count == 4


def test_a_manifest_that_is_not_a_list_of_records_is_refused(tmp_path: Path) -> None:
    """A shape change absorbed quietly looks identical to a corpus that holds nothing."""
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"filings": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="not a list"):
        CorpusFilingCatalog.from_manifest(path)


def test_an_exact_ticker_match_ranks_above_a_name_match(tmp_path: Path) -> None:
    """A user who typed four capital letters meant a ticker, and the ordering has to say so.

    Both issuers match "NOVA" here — one by its recorded ticker, one because its name contains the
    word — and the ticker holder comes first.
    """
    results = catalog(tmp_path).search_entities("NOVA")
    assert [e.name for e in results] == ["Zenith Holdings Inc", "Nova Industries Inc"]
    assert results[0].tickers == ("NOVA",)


def test_the_search_is_case_insensitive_in_both_directions(tmp_path: Path) -> None:
    """A selector that only matched the corpus's own capitalisation would find almost nothing."""
    found = catalog(tmp_path)
    assert [e.cik for e in found.search_entities("nova")] == [ZENITH, NOVA]
    assert [e.cik for e in found.search_entities("ZENITH HOLDINGS")] == [ZENITH]


def test_a_former_name_matches_because_issuers_are_remembered_by_the_name_they_filed_under(
    tmp_path: Path,
) -> None:
    """A 1996 filing was filed under a name EDGAR no longer shows, and users search for that name.

    The corpus spans six transport eras. Matching only the current name would make the older half of
    it unreachable from the one thing a user actually remembers.
    """
    results = catalog(tmp_path).search_entities(HALCYON_FORMER)
    assert [e.cik for e in results] == [NOVA]
    assert HALCYON_FORMER in results[0].former_names


def test_no_ticker_is_invented_for_an_issuer_whose_manifest_records_none(tmp_path: Path) -> None:
    """68 of the 112 corpus issuers have no current ticker, and none is reconstructed for them.

    A plausible-looking symbol in a selector is fabricated identity: it would be displayed, searched
    and eventually cited as though EDGAR had returned it.
    """
    found = catalog(tmp_path)
    nova = found.entity(NOVA)
    assert nova is not None
    assert nova.tickers == ()
    assert found.search_entities("NVI") == [], (
        "a ticker the manifest never recorded matches nothing"
    )
    assert [e.cik for e in found.search_entities("Nova Industries")] == [NOVA]


def test_a_query_matching_nothing_returns_nothing_rather_than_a_default(tmp_path: Path) -> None:
    """An empty or unmatched query must not fall back to "everything we have"."""
    found = catalog(tmp_path)
    assert found.search_entities("") == []
    assert found.search_entities("   ") == []
    assert found.search_entities("an issuer nobody preserved") == []


def test_an_issuer_with_no_qualifying_filing_never_appears(tmp_path: Path) -> None:
    """The catalog offers only what this project can actually process.

    A search control that offers an issuer the product cannot serve is worse than one that offers
    less. The manifest IS the qualifying set, so an issuer with no qualifying filing has no row —
    and the second half of this test proves the absence is caused by the missing filing rather than
    by the name never matching anything.
    """
    without = catalog(tmp_path / "without", ZENITH_ROWS)
    assert without.entity(NOVA) is None
    assert without.search_entities("Nova Industries") == []
    assert without.search_entities(HALCYON_FORMER) == []

    with_filing = catalog(tmp_path / "with", ZENITH_ROWS + NOVA_ROWS)
    assert with_filing.entity(NOVA) is not None
    assert [e.cik for e in with_filing.search_entities("Nova Industries")] == [NOVA]


def test_filings_are_returned_newest_first(tmp_path: Path) -> None:
    """A timeframe control that offered the oldest filing first would misread as a stale corpus."""
    dates = [f.filing_date for f in catalog(tmp_path).filings(ZENITH)]
    assert dates == ["2024-11-15", "2022-05-10", "2019-02-01"]


def test_filings_honour_the_from_and_to_date_bounds(tmp_path: Path) -> None:
    """The timeframe is the user's scope, and a run bills one invocation per filing inside it.

    A bound applied loosely is not a display defect: it is filings nobody asked for, each one
    separately billable.
    """
    found = catalog(tmp_path)
    assert [f.filing_date for f in found.filings(ZENITH, from_date="2020-01-01")] == [
        "2024-11-15",
        "2022-05-10",
    ]
    assert [f.filing_date for f in found.filings(ZENITH, to_date="2022-12-31")] == [
        "2022-05-10",
        "2019-02-01",
    ]
    assert [
        f.filing_date for f in found.filings(ZENITH, from_date="2020-01-01", to_date="2023-01-01")
    ] == ["2022-05-10"]


def test_the_date_bounds_are_inclusive_at_both_ends(tmp_path: Path) -> None:
    """MUTATION GUARD: a bound set to a filing's own date must not exclude that filing.

    An exclusive comparison would silently drop the boundary filing, which is the one a user asking
    for "the 2022 quarter" most obviously meant.
    """
    found = catalog(tmp_path)
    assert [
        f.accession for f in found.filings(ZENITH, from_date="2022-05-10", to_date="2022-05-10")
    ] == ["0000000101-22-000001"]


def test_a_bound_outside_the_corpus_returns_nothing_rather_than_everything(tmp_path: Path) -> None:
    """MUTATION GUARD: an ignored bound would return the whole issuer instead of an empty range."""
    assert catalog(tmp_path).filings(ZENITH, from_date="2030-01-01") == []


def test_entity_reports_the_earliest_and_latest_filing_so_a_timeframe_can_be_bounded(
    tmp_path: Path,
) -> None:
    """A timeframe control needs real limits, or it invites a range the corpus cannot serve.

    The dates are the issuer's own preserved extremes rather than a global corpus span, so the
    control cannot offer a year in which this issuer filed nothing.
    """
    entity = catalog(tmp_path).entity(ZENITH)
    assert entity is not None
    assert entity.earliest_filing_date == "2019-02-01"
    assert entity.latest_filing_date == "2024-11-15"
    assert entity.filing_count == 3
    assert entity.forms_present == ("10-K", "10-Q")
    assert entity.earliest_filing_date < entity.latest_filing_date


def test_a_single_filing_issuer_reports_the_same_date_at_both_ends(tmp_path: Path) -> None:
    """MUTATION GUARD: the extremes are computed, not read from the first and last manifest rows.

    An issuer with exactly one preserved filing has an earliest that equals its latest, and a
    control built on those two values must still bound to that one date.
    """
    entity = catalog(tmp_path).entity(NOVA)
    assert entity is not None
    assert entity.earliest_filing_date == entity.latest_filing_date == "2021-07-07"
    assert entity.filing_count == 1


def test_identity_is_normalised_on_the_way_in_and_on_the_way_out(tmp_path: Path) -> None:
    """CIK and accession normalization has exactly one home, and the catalog uses it.

    A lookup that matched only the padded CIK or only the dashed accession would miss half its
    callers and report the filing as absent — which reads as a corpus gap rather than a key bug.
    """
    found = catalog(tmp_path)
    assert found.filing("101", "0000000101-24-000001") is not None
    assert found.filing(ZENITH, "000000010124000001") is not None
    assert found.entity("101") is not None
    record = found.filing(101, "0000000101-24-000001")
    assert record is not None
    assert record.cik == ZENITH
    assert record.accession == "0000000101-24-000001"


def test_a_filing_the_corpus_does_not_hold_returns_none(tmp_path: Path) -> None:
    """An absent filing is reported as absent, never as an empty or nearby record."""
    found = catalog(tmp_path)
    assert found.filing(ZENITH, "0000000101-24-000099") is None
    assert found.filing(NOVA, "0000000101-24-000001") is None, "a filing belongs to one issuer"
    assert found.filings("303") == []


def test_a_filing_record_carries_the_preserved_artifacts_and_its_transport_era(
    tmp_path: Path,
) -> None:
    """A run cannot assemble a source set from a record that lost the files it names.

    The era travels with it because acquisition strategy differs by era; a record that dropped it
    would send a 1996 submission down the inline-XBRL path.
    """
    record = catalog(tmp_path).filing(ZENITH, "0000000101-24-000001")
    assert record is not None
    assert record.transport_era == "inline_xbrl"
    assert len(record.files) == 1
    assert record.files[0].filename == "primary.htm"
    assert record.files[0].byte_count == 4096
    assert record.files[0].local_path == "corpus/primary.htm"
    assert record.to_mapping()["accession"] == "0000000101-24-000001"


def test_a_file_entry_missing_its_name_or_path_is_dropped_rather_than_half_recorded(
    tmp_path: Path,
) -> None:
    """A preserved file with no local path cannot be read, and a placeholder for it is a lie.

    The record still exists — the filing is real — but it carries only artifacts that can actually
    be opened, so an assembler never resolves a name to nothing.
    """
    rows = [dict(NOVA_ROWS[0])]
    rows[0]["files"] = [
        {"filename": "primary.htm", "sha256": "0" * 64, "raw_bytes": 10, "local_path": ""},
        {
            "filename": "exhibit.htm",
            "sha256": "1" * 64,
            "raw_bytes": 20,
            "local_path": "corpus/exhibit.htm",
        },
    ]
    record = catalog(tmp_path, rows).filing(NOVA, "0000000202-21-000001")
    assert record is not None
    assert [f.filename for f in record.files] == ["exhibit.htm"]


def test_every_billable_attempt_is_reserved_separately(tmp_path: Path) -> None:
    """A retry is a second provider call and a second charge.

    Reserving once and then retrying would spend twice against a ceiling that had been checked
    once — the exact shape of the SDK-retry defect Phase 2 found underneath the ledger, one layer
    higher. This asserts the journal's own arithmetic supports it: two reservations accumulate, and
    the reservation for an attempt that failed is NOT released, because that request was issued and
    cost money.
    """
    journal = SpendJournal(FilesystemObjectStore(tmp_path / "store"), ceiling_usd=Decimal("1.00"))
    price = PriceInputs(
        input_per_1k=Decimal("0.001"),
        output_per_1k=Decimal("0.002"),
        currency="USD",
        source="test",
        effective_date="2026-08-03",
    )
    first = journal.authorize(
        price,
        max_input_tokens=1000,
        max_output_tokens=1000,
        at="2026-08-03T00:00:00Z",
        run_id="run_a",
        job_id="job_a",
        model_label="Model One",
    )
    second = journal.authorize(
        price,
        max_input_tokens=1000,
        max_output_tokens=1000,
        at="2026-08-03T00:00:01Z",
        run_id="run_a",
        job_id="job_a",
        model_label="Model One",
    )
    assert first == second == Decimal("0.003")
    assert journal.spent_usd == Decimal("0.006"), (
        "two attempts must accumulate two reservations; one reservation for two calls is a "
        "ceiling enforced against half the bill"
    )

    # Settling the SECOND attempt against measured usage must not release the FIRST.
    journal.settle(
        price,
        reserved=second,
        input_tokens=500,
        output_tokens=100,
        at="2026-08-03T00:00:02Z",
        run_id="run_a",
        job_id="job_a",
        model_label="Model One",
    )
    assert journal.spent_usd == Decimal("0.0037"), (
        "the failed attempt's reservation was released; a billable request that failed still "
        f"cost money. spent={journal.spent_usd}"
    )
