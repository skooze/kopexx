"""Server-rendered pages for the parser-review UI.

Two things about a filing are true at once: it is the authoritative source of everything this
product says, and it is untrusted input from the open internet. Rendering here escapes every value
exactly once and never hands filing bytes to a markup parser, which is what lets the content
security policy stay strict and removes the need for a sanitizer or a sandboxed iframe.

Nothing in this package is a build artifact. There is no bundler, no npm dependency and no build
step: the stylesheet and the single script are module constants served from their own routes.
"""

from .assets import SCRIPT, STYLESHEET
from .html import badge, each, esc, join, tag, warning
from .job_view import RAW_WINDOW_CHARACTERS, job_page, parsed_pane, raw_pane
from .views import home, layout, preflight_page, run_page, search_panel

__all__ = [
    "RAW_WINDOW_CHARACTERS",
    "SCRIPT",
    "STYLESHEET",
    "badge",
    "each",
    "esc",
    "home",
    "job_page",
    "join",
    "layout",
    "parsed_pane",
    "preflight_page",
    "raw_pane",
    "run_page",
    "search_panel",
    "tag",
    "warning",
]
