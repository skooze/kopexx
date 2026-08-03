"""The stylesheet and the one script, held as module constants and served from their own routes.

WHY CONSTANTS AND NOT FILES. `pyproject.toml` records that `packages/` contains zero non-Python
files and therefore needs no package-data configuration. Keeping the assets here preserves that,
ships them in the wheel automatically, puts them under `ruff` and the coverage measurement, and
removes an entire class of defect: there is no static-file route, so there is no path to traverse.

WHY NOT INLINE IN THE PAGE. Inline style and script would force `unsafe-inline` into the content
security policy, and the policy is the reason a preserved SEC filing can be displayed at all
without a sanitizer. Two extra requests on loopback is a cheap price for `style-src 'self'`.

VISUAL DESIGN, FROM `docs/dashboard/ux-specification.md`. Light mode. Light and dark grey surfaces.
Dark grey menus and tables. Soft translucent blue and green accents, never a fully saturated block
of colour. The Run button is the single strongest accent on the page and is still semi-transparent.
Status is never carried by colour alone: every marker has a text equivalent beside it.
"""

from __future__ import annotations

from typing import Final

STYLESHEET: Final[str] = """
:root {
  --surface:        #f4f5f7;
  --surface-raised: #ffffff;
  --surface-sunken: #e8eaed;
  --panel:          #3a3f45;
  --panel-text:     #e9ecef;
  --panel-muted:    #a8b0b8;
  --ink:            #22262b;
  --ink-muted:      #5d656e;
  --rule:           #d4d8dd;
  --accent-blue:    rgba(88, 140, 214, 0.22);
  --accent-blue-in: rgba(88, 140, 214, 0.42);
  --accent-green:   rgba(78, 160, 110, 0.20);
  --accent-amber:   rgba(198, 146, 44, 0.22);
  --accent-red:     rgba(190, 90, 90, 0.20);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font: 14px/1.55 "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
  color: var(--ink);
  background: var(--surface);
  display: flex;
  min-height: 100vh;
}

a { color: #2f5d99; }
h1, h2, h3 { font-weight: 600; letter-spacing: -0.01em; margin: 0 0 .6rem; }
h1 { font-size: 1.15rem; }
h2 { font-size: 1rem; }
h3 { font-size: .9rem; }

/* --- left search panel ------------------------------------------------------------------- */

.panel {
  width: 320px;
  min-width: 320px;
  background: var(--panel);
  color: var(--panel-text);
  padding: 1rem 1rem 4.5rem;
  position: relative;
  overflow-y: auto;
}
.panel.collapsed { display: none; }
.panel h1 { color: #fff; font-size: 1rem; }
.panel label { display: block; margin: .85rem 0 .2rem; font-size: .74rem;
               text-transform: uppercase; letter-spacing: .07em; color: var(--panel-muted); }
.panel input, .panel select {
  width: 100%; padding: .42rem .5rem; border-radius: 5px;
  border: 1px solid #4e545b; background: #2f343a; color: var(--panel-text); font-size: .85rem;
}
.panel select:disabled, .panel input:disabled { opacity: .55; }
.panel .hint { font-size: .74rem; color: var(--panel-muted); margin: .3rem 0 0; }

.collapse-control {
  position: absolute; top: .7rem; right: .7rem;
  background: transparent; border: 1px solid #575e66; color: var(--panel-text);
  border-radius: 5px; padding: .1rem .45rem; cursor: pointer; text-decoration: none;
}

.run-button {
  display: block; width: 100%; margin-top: 1.1rem; padding: .6rem;
  background: var(--accent-blue-in); color: #fff;
  border: 1px solid rgba(120, 170, 235, .55); border-radius: 6px;
  font-size: .92rem; font-weight: 600; cursor: pointer;
}
.run-button:disabled { background: rgba(120, 130, 145, .28); border-color: #5a616a;
                       color: var(--panel-muted); cursor: not-allowed; }

/* --- the run identifier, anchored to the viewport --------------------------------------- */

.run-id {
  position: fixed; left: 0; bottom: 0; z-index: 10;
  background: #2f343a; color: var(--panel-text);
  border-top: 1px solid #4e545b; border-right: 1px solid #4e545b;
  padding: .4rem .6rem; font-size: .76rem; font-family: ui-monospace, monospace;
  display: flex; gap: .5rem; align-items: center; max-width: 320px;
}
.run-id a { color: #cfe0f7; }
.run-id button { background: #3f454c; color: var(--panel-text); border: 1px solid #575e66;
                 border-radius: 4px; font-size: .72rem; padding: .1rem .4rem; cursor: pointer; }

/* --- main workspace --------------------------------------------------------------------- */

main { flex: 1; padding: 1.1rem 1.4rem 3.5rem; overflow-x: auto; }
.reopen { display: inline-block; margin-bottom: .8rem; padding: .2rem .55rem;
          border: 1px solid var(--rule); border-radius: 5px; background: var(--surface-raised);
          text-decoration: none; color: var(--ink); }

.card { background: var(--surface-raised); border: 1px solid var(--rule);
        border-radius: 8px; padding: .85rem 1rem; margin-bottom: .9rem; }

table { border-collapse: collapse; width: 100%; font-size: .82rem; }
th, td { text-align: left; padding: .34rem .5rem; border-bottom: 1px solid var(--rule);
         vertical-align: top; }
thead { background: var(--panel); color: var(--panel-text); }
thead th { border-bottom: none; font-weight: 600; }
.scroll-x { overflow-x: auto; }

.badge { display: inline-block; padding: .05rem .42rem; border-radius: 999px;
         font-size: .72rem; border: 1px solid var(--rule); background: var(--surface-sunken); }
.badge-ok   { background: var(--accent-green); }
.badge-info { background: var(--accent-blue); }
.badge-warn { background: var(--accent-amber); }
.badge-bad  { background: var(--accent-red); }

.warning { background: var(--accent-amber); border-left: 3px solid rgba(198,146,44,.8);
           padding: .45rem .7rem; margin: .5rem 0; border-radius: 0 5px 5px 0; }

.views { display: flex; gap: .4rem; margin-bottom: .8rem; flex-wrap: wrap; }
.views a { padding: .28rem .7rem; border: 1px solid var(--rule); border-radius: 6px;
           background: var(--surface-raised); text-decoration: none; color: var(--ink); }
.views a.active { background: var(--accent-blue); border-color: rgba(88,140,214,.55);
                  font-weight: 600; }

.panes { display: flex; gap: .8rem; align-items: flex-start; }
.panes > section { flex: 1 1 0; min-width: 0; }

pre.source {
  background: var(--surface-sunken); border: 1px solid var(--rule); border-radius: 6px;
  padding: .7rem; max-height: 68vh; overflow: auto; font-size: .76rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap; word-break: break-word;
}
pre.source mark { background: var(--accent-blue-in); }

.node { border-left: 3px solid var(--accent-blue-in); padding: .1rem 0 .1rem .7rem;
        margin: .7rem 0; }
.node .kind { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em;
              color: var(--ink-muted); }
.node .title { font-weight: 600; }
.node .body { margin: .3rem 0; }
.refs { font-size: .76rem; color: var(--ink-muted); }
.refs li { margin: .12rem 0; }

form.inline { display: flex; gap: .4rem; flex-wrap: wrap; align-items: flex-start; }
form.inline textarea { flex: 1 1 22rem; min-height: 3.4rem; padding: .4rem;
                       border: 1px solid var(--rule); border-radius: 5px; font: inherit; }
form.inline select, form.inline button, form.inline input[type=text] {
  padding: .35rem .55rem; border: 1px solid var(--rule); border-radius: 5px;
  background: var(--surface-raised); font: inherit;
}
form.inline button { background: var(--accent-blue); cursor: pointer; font-weight: 600; }

.mode-note { font-size: .76rem; color: var(--ink-muted); margin-top: 1.4rem; }
.mono { font-family: ui-monospace, monospace; font-size: .78rem; }
"""

SCRIPT: Final[str] = """
// The only script in the application. It copies the run identifier and nothing else.
//
// Everything that matters here works with scripting disabled: the raw and parsed views, the
// side-by-side view, source-reference navigation, comments and review actions are ordinary links
// and form posts rendered by the server. That is not nostalgia — it means the review surface has
// no client-side state to lose, no rendering path that can disagree with what was stored, and no
// way for a preserved filing to reach a JavaScript context at all.
(function () {
  "use strict";
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy]");
    if (!button) { return; }
    var value = button.getAttribute("data-copy");
    var done = function () {
      var previous = button.textContent;
      button.textContent = "copied";
      window.setTimeout(function () { button.textContent = previous; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(done, function () {});
    }
  });
})();
"""
