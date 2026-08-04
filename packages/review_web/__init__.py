"""Server-rendered pages for the parser-review UI.

Two things about a filing are true at once: it is the authoritative source of everything this
product says, and it is untrusted input from the open internet. Rendering here escapes every value
exactly once and never hands filing bytes to a markup parser, which is what lets the content
security policy stay strict and removes the need for a sanitizer or a sandboxed iframe.

Nothing in this package is a build artifact. There is no bundler, no npm dependency and no build
step: the stylesheet and the single script are module constants served from their own routes.
"""

from .assets import SCRIPT, STYLESHEET
from .benchmark_view import (
    KIND_CLASSIFICATIONS,
    SPAN_TEXT_CHARACTERS,
    SPANS_PER_PAGE,
    TABLE_SLICE_CHARACTERS,
    base_path,
    benchmark_index,
    images_page,
    inventory_page,
    spans_page,
    tables_page,
)
from .html import badge, each, esc, join, tag, url, warning
from .job_view import RAW_WINDOW_CHARACTERS, job_page, parsed_pane, raw_pane
from .model_comparison_view import (
    OMITTED_SPANS_SHOWN,
    TABLES_SHOWN,
    model_comparison_page,
    model_run_page,
    models_base,
)
from .multipart_view import assembled_page, multipart_page, task_page
from .views import (
    BENCHMARK_TAB,
    FILING_TAB,
    home,
    layout,
    preflight_page,
    run_page,
    search_panel,
    tabs,
)

__all__ = [
    "KIND_CLASSIFICATIONS",
    "OMITTED_SPANS_SHOWN",
    "RAW_WINDOW_CHARACTERS",
    "SCRIPT",
    "SPANS_PER_PAGE",
    "SPAN_TEXT_CHARACTERS",
    "STYLESHEET",
    "TABLES_SHOWN",
    "TABLE_SLICE_CHARACTERS",
    "assembled_page",
    "badge",
    "base_path",
    "benchmark_index",
    "each",
    "esc",
    "home",
    "images_page",
    "inventory_page",
    "job_page",
    "join",
    "BENCHMARK_TAB",
    "FILING_TAB",
    "layout",
    "tabs",
    "model_comparison_page",
    "model_run_page",
    "models_base",
    "multipart_page",
    "parsed_pane",
    "preflight_page",
    "raw_pane",
    "run_page",
    "search_panel",
    "spans_page",
    "tables_page",
    "tag",
    "task_page",
    "url",
    "warning",
]
