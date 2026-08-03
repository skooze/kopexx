"""Accession document inventory and classification.

CLASSIFICATION IS BY THE FILER'S DECLARED TYPE, NOT THE FILENAME. Apple names its Rule 13a-14(a)
certification `a10-kexhibit31109272025.htm`, from which "exhibit 31.1" is recoverable only by
assuming where `311` splits. The accession index table carries `EX-31.1` directly.
"""

from __future__ import annotations

import pytest

from packages.filing_acquisition.inventory import (
    GRAPHIC,
    HUMAN_READABLE,
    MACHINE_ARTIFACT,
    ROLE_CERTIFICATION,
    ROLE_COMPLETE_SUBMISSION,
    ROLE_CONSENT,
    ROLE_EXHIBIT,
    ROLE_GRAPHIC,
    ROLE_MACHINE,
    ROLE_OTHER,
    ROLE_PRIMARY,
    UNKNOWN,
    classify,
    filing_index_url,
    folder_filenames,
    parse_filing_index,
)

PRIMARY = "aapl-20250927.htm"

# The shape SEC's accession index page actually emits: two tables, filed documents then data
# files, each row Seq / Description / Document / Type / Size.
INDEX_HTML = """
<table><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
<tr><td>1</td><td>10-K</td><td>aapl-20250927.htm &nbsp;&nbsp;iXBRL</td><td>10-K</td><td>1520208</td></tr>
<tr><td>2</td><td>EX-4.1</td><td>a10-kexhibit4109272025.htm</td><td>EX-4.1</td><td>118590</td></tr>
<tr><td>4</td><td>EX-23.1</td><td>a10-kexhibit23109272025.htm</td><td>EX-23.1</td><td>6251</td></tr>
<tr><td>5</td><td>EX-31.1</td><td>a10-kexhibit31109272025.htm</td><td>EX-31.1</td><td>10507</td></tr>
<tr><td>13</td><td></td><td>aapl-20250927_g1.jpg</td><td>GRAPHIC</td><td>10963</td></tr>
<tr><td></td><td>Complete submission text file</td><td>0000320193-25-000079.txt</td><td></td><td>9392337</td></tr>
</table>
<table><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
<tr><td>8</td><td>XBRL TAXONOMY EXTENSION SCHEMA DOCUMENT</td><td>aapl-20250927.xsd</td><td>EX-101.SCH</td><td>56313</td></tr>
</table>
"""


def _inventory():
    return parse_filing_index(
        INDEX_HTML,
        accession="0000320193-25-000079",
        cik="0000320193",
        primary_document=PRIMARY,
    )


def test_every_filed_document_is_parsed_from_the_index() -> None:
    inventory = _inventory()
    assert [e.filename for e in inventory.entries] == [
        PRIMARY,
        "a10-kexhibit4109272025.htm",
        "a10-kexhibit23109272025.htm",
        "a10-kexhibit31109272025.htm",
        "aapl-20250927_g1.jpg",
        "0000320193-25-000079.txt",
        "aapl-20250927.xsd",
    ]


def test_nothing_is_ambiguous_on_a_real_index() -> None:
    assert _inventory().ambiguities == []


def test_the_renderer_annotation_does_not_become_part_of_the_filename() -> None:
    """The Document cell carries a trailing `iXBRL` badge the renderer adds."""
    assert _inventory().entries[0].filename == PRIMARY


def test_a_certification_is_classified_by_declared_type_not_filename() -> None:
    """REGRESSION: filename classification put all six certifications in `other_filed_attachment`."""
    entry = next(e for e in _inventory().entries if e.declared_type == "EX-31.1")
    assert entry.role == ROLE_CERTIFICATION
    assert entry.document_class == HUMAN_READABLE
    assert entry.requires_content_extraction
    assert entry.classification_method == "declared_type"


def test_a_consent_is_distinguished_from_an_ordinary_exhibit() -> None:
    inventory = _inventory()
    assert next(e for e in inventory.entries if e.declared_type == "EX-23.1").role == ROLE_CONSENT
    assert next(e for e in inventory.entries if e.declared_type == "EX-4.1").role == ROLE_EXHIBIT


def test_xbrl_taxonomy_exhibits_are_machine_evidence() -> None:
    """`EX-101.*` is a filed exhibit and still never model-visible."""
    entry = next(e for e in _inventory().entries if e.declared_type == "EX-101.SCH")
    assert entry.document_class == MACHINE_ARTIFACT
    assert entry.role == ROLE_MACHINE
    assert not entry.requires_content_extraction


def test_the_complete_submission_text_is_never_extracted() -> None:
    """It concatenates every other document; extracting it double-counts the whole filing."""
    entry = next(e for e in _inventory().entries if e.filename.endswith("-25-000079.txt"))
    assert entry.role == ROLE_COMPLETE_SUBMISSION
    assert not entry.requires_content_extraction
    assert "double-count" in entry.classification_reason


def test_a_graphic_is_inventoried_but_not_extracted() -> None:
    entry = next(e for e in _inventory().entries if e.document_class == GRAPHIC)
    assert entry.role == ROLE_GRAPHIC
    assert not entry.requires_content_extraction
    assert "alt text" in entry.classification_reason


def test_the_primary_document_is_flagged() -> None:
    entry = _inventory().entries[0]
    assert entry.role == ROLE_PRIMARY
    assert entry.requires_content_extraction


def test_a_courtesy_pdf_is_not_extracted_alongside_the_document_it_duplicates() -> None:
    """REGRESSION: a courtesy PDF carries the SAME declared type as the primary it duplicates.

    Apple files `aapl_courtesy-pdf.pdf` beside its DEF 14A; extracting both would double-count the
    entire proxy.
    """
    document_class, role, extract, _method, reason = classify(
        "aapl_courtesy-pdf.pdf", "DEF 14A", primary_document="aapl014016-def14a.htm"
    )
    assert document_class == HUMAN_READABLE
    assert role == ROLE_OTHER
    assert not extract
    assert "alternate rendering" in reason


def test_an_unrecognisable_file_is_ambiguous_rather_than_guessed() -> None:
    document_class, _role, extract, method, reason = classify(
        "mystery.dat", "", primary_document=PRIMARY
    )
    assert document_class == UNKNOWN
    assert not extract
    assert method == "unclassified"
    assert "rather than guessed" in reason


def test_a_size_that_sec_leaves_empty_does_not_raise() -> None:
    """`int("")` raises, and any folder total computed from it under-counts."""
    html = (
        "<table><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>"
        "<tr><td>1</td><td>10-K</td><td>x.htm</td><td>10-K</td><td></td></tr></table>"
    )
    inventory = parse_filing_index(
        html,
        accession="0000320193-25-000079",
        cik="0000320193",
        primary_document="x.htm",
    )
    assert inventory.entries[0].listed_size is None


def test_the_folder_listing_is_a_superset_of_the_filed_documents() -> None:
    """`index.json` also holds SEC's own viewer output, which nobody filed."""
    payload = (
        '{"directory":{"item":['
        '{"name":"aapl-20250927.htm"},{"name":"R1.htm"},{"name":"MetaLinks.json"}]}}'
    )
    assert folder_filenames(payload) == ["aapl-20250927.htm", "R1.htm", "MetaLinks.json"]


def test_the_index_url_is_built_from_the_issuer_cik() -> None:
    """Never the accession prefix, which belongs to the filing agent."""
    url = filing_index_url("0000320193", "0001308179-26-000008")
    assert "/data/320193/" in url
    assert url.endswith("0001308179-26-000008-index.html")


def test_census_separates_filed_documents_from_renderer_artifacts() -> None:
    inventory = _inventory()
    inventory.renderer_artifacts = ["R1.htm", "R2.htm"]
    census = inventory.census()
    assert census["filed_documents"] == 7
    assert census["renderer_artifacts"] == 2
    assert census["requires_extraction"] == 4
    assert census["ambiguous"] == 0


@pytest.mark.parametrize(
    ("declared", "expected_role"),
    [
        ("EX-32.1", ROLE_CERTIFICATION),
        ("EX-31.2", ROLE_CERTIFICATION),
        ("EX-23", ROLE_CONSENT),
        ("EX-10.1", ROLE_EXHIBIT),
        ("EX-101.PRE", ROLE_MACHINE),
    ],
)
def test_declared_type_drives_the_role(declared: str, expected_role: str) -> None:
    _class, role, _extract, _method, _reason = classify(
        "somefile.htm", declared, primary_document=PRIMARY
    )
    assert role == expected_role
