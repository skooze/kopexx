"""Regenerate the committed table-ownership fixtures from the preserved filings.

    python scripts/build_ownership_fixtures.py

Writes `tests/fixtures/filings/<accession>/table-ownership.json` for every acquired filing.

WHY A DERIVED FIXTURE RATHER THAN THE SOURCE DOCUMENTS. Ownership needs three things from a
filing: where each table sits, where each tagged narrative span sits, and which presentation roles
each concept belongs to. Committing the sources that carry them means about 6 MB of primary
documents and half a megabyte of linkbase per filing, permanently in history, for content SEC
hosts authoritatively. The extracted geometry is a few hundred kilobytes of text that diffs
cleanly in review.

WHAT MAKES IT REAL. Every offset, span, and concept is read from the preserved bytes; nothing is
invented. The expected classification recorded alongside is what the implementation produced
against those bytes, so the regression compares the code to a measurement rather than to a guess.
Regenerating requires `var/objects`, so a fixture cannot drift without someone running this.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.footnote_canonicalizer import PARSER_VERSION as CANONICALIZER_VERSION  # noqa: E402
from packages.footnote_canonicalizer import (  # noqa: E402
    ExclusionList,
    canonicalize,
    classify_tables,
)
from packages.footnote_extractor import (  # noqa: E402
    find_tagged_spans,
    read_headings,
    read_inventory,
    read_presentation_from_package,
    text_block_spans,
)
from packages.storage import sha256_file  # noqa: E402
from packages.table_parser import PARSER_VERSION as TABLE_PARSER_VERSION  # noqa: E402
from packages.table_parser import parse_tables  # noqa: E402

DEFAULT_MANIFEST = REPO_ROOT / "var" / "acquisition.json"
DEFAULT_OBJECT_ROOT = REPO_ROOT / "var" / "objects"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "filings"


def build_for(record: dict, object_root: Path, exclusions: ExclusionList) -> dict:
    keys = {obj["role"]: obj["storage_key"] for obj in record["objects"]}
    inventory = read_inventory(object_root / keys["filing_summary"])
    primary = object_root / keys["primary_document"]
    raw = primary.read_text(encoding="utf-8", errors="replace")

    result = canonicalize(
        accession=record["accession"],
        inventory=inventory,
        headings=read_headings(primary),
        exclusions=exclusions,
    )
    spans = text_block_spans(raw)
    numeric = [s for s in find_tagged_spans(raw) if s.tag == "ix:nonfraction"]
    linkbase = read_presentation_from_package(object_root / keys["xbrl_package"])
    statement_roles = {
        r.role for r in inventory.real_reports if r.menu_category == "Statements" and r.role
    }
    tables = parse_tables(raw)
    ownership = classify_tables(
        result,
        tables,
        spans,
        linkbase,
        statement_roles=statement_roles,
        numeric_spans=numeric,
    )

    numeric_concepts = {s.concept for s in numeric}
    return {
        "accession": record["accession"],
        # PROVENANCE. A derived fixture is only as trustworthy as its ability to name the bytes it
        # came from. Each source object is recorded with the SHA-256 of the file this run actually
        # read, so a reviewer can confirm the fixture matches the preserved filing and a rebuild
        # against different bytes is detectable rather than silent.
        "provenance": {
            "generated_by": "python scripts/build_ownership_fixtures.py",
            "form": record.get("form"),
            "sources": [
                {
                    "role": role,
                    "storage_key": keys[role],
                    "sha256": sha256_file(object_root / keys[role]),
                    "size_bytes": (object_root / keys[role]).stat().st_size,
                }
                for role in ("primary_document", "xbrl_package", "filing_summary")
            ],
            "parser_versions": {
                "canonicalizer": CANONICALIZER_VERSION,
                "table_parser": TABLE_PARSER_VERSION,
            },
            "note": (
                "Derived geometry only: table offsets, tagged-span ranges, and the concept-to-role "
                "index. The complete source documents are NOT committed; SEC hosts them "
                "authoritatively and the hashes above pin exactly which bytes were read."
            ),
        },
        "tables": [
            {
                "external_id": t.external_id,
                "source_offset": t.source_offset,
                "raw_length": len(t.raw_html),
            }
            for t in tables
        ],
        "text_block_spans": [
            {
                "concept": s.concept,
                "start": s.start,
                "end": s.end,
                "is_continuation": s.is_continuation,
            }
            for s in spans
        ],
        "numeric_spans": [{"concept": s.concept, "start": s.start} for s in numeric],
        "statement_roles": sorted(statement_roles),
        # Only the concepts ownership consults: narrative blocks and the numeric concepts that
        # identify a statement. Carrying the whole index would triple the fixture for no gain.
        "concept_roles": {
            concept: sorted(roles)
            for concept, roles in linkbase.concept_to_roles().items()
            if concept.endswith("TextBlock") or concept in numeric_concepts
        },
        "expected_ownership": {
            o.external_id: {
                "classification": o.classification,
                "owner_role_uri": o.owner_role_uri,
            }
            for o in ownership.ownership
        },
        "expected_census": ownership.as_record(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--object-root", type=Path, default=DEFAULT_OBJECT_ROOT)
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        print(
            f"no acquisition manifest at {args.manifest}. Fixtures are regenerated from the "
            "preserved filings, which are not committed.",
            file=sys.stderr,
        )
        return 2

    exclusions = ExclusionList.load()
    for record in json.loads(args.manifest.read_text(encoding="utf-8")):
        fixture = build_for(record, args.object_root, exclusions)
        target = FIXTURE_ROOT / record["accession"] / "table-ownership.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(fixture, indent=1, sort_keys=True), encoding="utf-8")
        census = fixture["expected_census"]
        print(
            f"  {record['accession']}  tables={census['total']}"
            f"  footnote-owned={census['canonical_footnote']}"
            f"  unresolved={census['unresolved']}"
            f"  -> {target.stat().st_size / 1024:.0f} KB"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
