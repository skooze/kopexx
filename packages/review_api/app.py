"""Assemble the parser-review application from validated settings.

WIRING IS THE ONLY THING THIS MODULE DOES, and it is the only place that knows every part exists.
Each package it touches refuses a bad configuration on its own terms — `ReviewSettings` refuses a
LAN bind without a secret, `LlmSettings` refuses a real provider without a region, the capability
catalog refuses to run without a supplied snapshot, the prompt registry refuses a prompt whose
bytes have moved — so assembling is where those refusals surface, at start-up, before anything
generates traffic or spends money.

THE PROVIDER IS SELECTED BY CONFIGURATION AND NEVER GUESSED. `LLM_PROVIDER=mock` is the default
and needs no credentials, no network and no region; anything else is an explicit choice by whoever
started the process. There is no fallback in either direction: a misconfigured real provider fails
at start-up rather than quietly running against the mock and producing evidence of nothing.

INTERRUPTED JOBS ARE MARKED AT START-UP AND NOTHING IS RESUMED. A process that came back up is not
a user who asked to spend money again.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from packages.configuration import ReviewSettings, Settings, validate_user_agent
from packages.evaluation_store import EvaluationStore
from packages.filing_acquisition import SecMemberFetcher
from packages.llm_gateway.providers.base import ModelProvider
from packages.llm_gateway.providers.mock import MockProvider
from packages.model_catalog import load_snapshot
from packages.orchestrator import (
    BenchmarkFilingCatalog,
    BoundedWorker,
    CompositeFilingCatalog,
    CorpusFilingCatalog,
    MultipartSettings,
    ParserReviewService,
    SpendJournal,
)
from packages.prompt_registry import PromptRegistry
from packages.sec_client import SecHttpClient
from packages.source_transport import (
    CompositeInventory,
    ManifestInventory,
    ObjectStoreInventory,
    PreservedObject,
    RefusingFetcher,
)
from packages.storage import FilesystemObjectStore

from .handlers import ReviewApp
from .security import SecurityPolicy
from .server import ReviewServer


@dataclass
class Application:
    """Everything a running instance holds, so a caller can shut it down cleanly."""

    app: ReviewApp
    service: ParserReviewService
    worker: Any
    server: ReviewServer | None = None

    def stop(self) -> None:
        if self.server is not None:
            self.server.stop()
        self.worker.shutdown()


def build_provider(settings: Settings) -> ModelProvider:
    """The provider named by configuration. No fallback in either direction."""
    if settings.llm.provider == "mock":
        return MockProvider()
    if settings.llm.provider == "bedrock":
        # Imported here so that a mock-configured instance never touches the adapter module and
        # never needs the optional AWS SDK installed at all.
        from packages.llm_gateway.providers.bedrock import BedrockProvider  # noqa: PLC0415

        return BedrockProvider()
    raise ValueError(
        f"unknown model provider {settings.llm.provider!r}. There is no default and no fallback: "
        "a provider that quietly became the mock would produce evidence of nothing."
    )


def _corpus_inventory(manifest_path: str | Path) -> ManifestInventory:
    """A read-only inventory over the preserved research corpus.

    Reads the same supplied manifest the catalog reads, so the two cannot describe different
    corpora — a filing offered in the search panel is one whose bytes the inventory can find.
    """
    import json  # noqa: PLC0415 - host state, never model-visible; see catalog.py

    records = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    entries: dict[tuple[str, str], list[PreservedObject]] = {}
    for row in records:
        objects = [
            PreservedObject(
                filename=str(f["filename"]),
                sha256=str(f["sha256"]),
                byte_count=int(f["raw_bytes"]),
                source_url=str(f.get("source_url") or ""),
                locator=str(f["local_path"]),
                acquired_at=str(row.get("acquisition_timestamp") or ""),
                acquisition_method="research_corpus",
                reused=True,
            )
            for f in (row.get("files") or ())
            if f.get("filename") and f.get("local_path")
        ]
        if objects:
            entries[(str(row["cik"]), str(row["accession"]))] = objects
    return ManifestInventory(entries)


def build(settings: Settings, *, provider: ModelProvider | None = None) -> Application:
    """Construct a ready instance. Raises at start-up on any invalid configuration."""
    review: ReviewSettings = settings.review
    validate_user_agent(settings.sec.user_agent)

    objects = FilesystemObjectStore(settings.storage.root)
    store = EvaluationStore.at_path(review.evaluation_root)
    journal = SpendJournal(
        FilesystemObjectStore(review.evaluation_root),
        ceiling_usd=Decimal(review.cost_ceiling_usd),
        phase=review.spend_phase,
        phase_ceiling_usd=(
            Decimal(review.phase_cost_ceiling_usd) if review.phase_cost_ceiling_usd else None
        ),
    )
    snapshot = load_snapshot(Path(review.capability_snapshot).read_text(encoding="utf-8"))
    prompts = PromptRegistry.from_directory(review.prompt_directory)
    catalog: Any = CorpusFilingCatalog.from_manifest(review.corpus_manifest)
    if review.benchmark_manifest and Path(review.benchmark_manifest).is_file():
        # THE BENCHMARK FILING IS NOT IN THE SAMPLED CORPUS AND MUST STILL BE REACHABLE.
        # Apple's 10-Q 0000320193-25-000008 is a preserved Sprint 3 fixture, not one of the 613
        # filings a Phase 0 sampling run happened to draw. A benchmark whose reachability
        # depended on that draw would be a benchmark nobody could reproduce.
        catalog = CompositeFilingCatalog(
            catalog, BenchmarkFilingCatalog.from_manifest(review.benchmark_manifest)
        )
    inventory = CompositeInventory(
        ObjectStoreInventory(objects), _corpus_inventory(review.corpus_manifest)
    )

    if review.allow_sec_fetch:
        fetcher: Any = SecMemberFetcher(
            SecHttpClient(
                settings.sec.user_agent,
                cooldown_seconds=settings.sec.throttle_cooldown_seconds,
            ),
            objects,
        )
    else:
        fetcher = RefusingFetcher()

    service = ParserReviewService(
        store=store,
        catalog=catalog,
        snapshot=snapshot,
        prompts=prompts,
        inventory=inventory,
        fetcher=fetcher,
        provider=provider or build_provider(settings),
        journal=journal,
        preferred_region=settings.llm.region or "",
        author=review.author_label,
        multipart_settings=MultipartSettings(
            max_depth=review.multipart_max_depth,
            max_reconciliation_cycles=review.multipart_reconciliation_cycles,
            filing_budget_usd=Decimal(review.multipart_filing_budget_usd),
            source_input_mode=review.source_input_mode,
        ),
    )

    # A restart never resumes billable work. Anything mid-flight becomes INTERRUPTED and waits for
    # a person; nothing is re-invoked. BOTH LEVELS, because a multipart parse can be mid-flight
    # at the task level while its child job sits perfectly still — and a completed part is kept,
    # so a resume reruns only the branch that was actually interrupted.
    store.mark_interrupted_jobs()
    store.mark_interrupted_tasks()

    worker = BoundedWorker(service, max_concurrency=review.max_concurrent_invocations)
    policy = SecurityPolicy(
        loopback_only=review.loopback_only,
        dev_auth_secret=review.dev_auth_secret,
        https=review.served_over_https,
        allowed_hosts=frozenset(review.allowed_hosts),
        authentication_disabled=review.public_unauthenticated,
    )
    return Application(
        app=ReviewApp(service=service, worker=worker, policy=policy),
        service=service,
        worker=worker,
    )


def serve(settings: Settings | None = None) -> None:
    """Start the review application. The entry point a developer runs."""
    resolved = settings or Settings.from_env(dict(os.environ))
    application = build(resolved)
    server = ReviewServer(
        application.app,
        host=resolved.review.bind_host,
        port=resolved.review.bind_port,
    )
    application.server = server
    mode = "loopback only" if resolved.review.loopback_only else "NETWORK INTERFACE"
    print(f"Kopexx parser review on {server.url}  ({mode})")  # noqa: T201 - the point of serving
    if not resolved.review.loopback_only and resolved.review.public_unauthenticated:
        # STATED EVERY TIME IT STARTS. An unauthenticated public instance is a decision, and a
        # decision nobody is reminded of is one that outlives the reason for it.
        names = ", ".join(resolved.review.allowed_hosts) or "ANY host name"
        print(  # noqa: T201
            f"PUBLISHED WITHOUT AUTHENTICATION, answering to {names}. Anyone who can reach it can "
            "read every preserved filing and every run's evidence, and can issue BILLABLE provider "
            f"calls bounded only by the spend ceiling of USD {resolved.review.cost_ceiling_usd}."
        )
    elif not resolved.review.loopback_only:
        print(  # noqa: T201
            "Bound beyond loopback. Authentication is required and this process speaks plain "
            "HTTP: terminate TLS in front of it, or prefer loopback plus an SSH tunnel."
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        application.stop()
