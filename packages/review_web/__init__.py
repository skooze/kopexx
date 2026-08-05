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
    CLASSIFICATION_KIND,
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
from .filings_view import filings_index, judgements_page
from .html import badge, each, esc, join, tag, url, warning
from .hub_view import hub
from .job_view import RAW_WINDOW_CHARACTERS, job_page, parsed_pane, raw_pane
from .model_comparison_view import (
    OMITTED_SPANS_SHOWN,
    TABLES_SHOWN,
    comparison_panes,
    model_comparison_page,
    model_run_page,
    models_base,
)
from .multipart_view import assembled_page, assembled_pane, multipart_page, task_page
from .nav import (
    FILING,
    PARSE,
    SEARCH,
    Crumb,
    active_section,
    crumbs,
    destination,
    global_nav,
    kind_word,
    mode_strip,
    panel_mode,
    panel_subject,
    scope_marker,
    with_query,
)
from .panel import PanelContext, ParseRow, TaskRow, review_menu
from .progress import (
    EARLIER,
    NEVER,
    OPENED,
    OPENED_NOTE,
    Counts,
    counts,
    counts_sentence,
    marker,
)
from .views import (
    BENCHMARK_TAB,
    FILING_TAB,
    home,
    layout,
    panel_shell,
    preflight_page,
    run_page,
    search_panel,
    tabs,
)

__all__ = [
    "CLASSIFICATION_KIND",
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
    "assembled_pane",
    "comparison_panes",
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
    "panel_shell",
    "hub",
    "review_menu",
    "PanelContext",
    "ParseRow",
    "TaskRow",
    "Crumb",
    "crumbs",
    "global_nav",
    "mode_strip",
    "panel_mode",
    "panel_subject",
    "active_section",
    "with_query",
    "destination",
    "scope_marker",
    "kind_word",
    "SEARCH",
    "PARSE",
    "FILING",
    "OPENED",
    "EARLIER",
    "NEVER",
    "OPENED_NOTE",
    "Counts",
    "counts",
    "counts_sentence",
    "marker",
    "filings_index",
    "judgements_page",
    "spans_page",
    "tables_page",
    "tag",
    "task_page",
    "url",
    "warning",
]
