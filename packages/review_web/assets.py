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

/* THE DASHBOARD'S TWO VIEWS. A tab strip and not a dropdown: both views are top-level, a person
   moves between them constantly, and a dropdown hides the fact that the second one exists. The
   active tab is carried by a filled surface AND by aria-current, never by colour alone — the
   stylesheet's own rule, and the reason every status marker here has a text equivalent. */
.tabs {
  display: flex;
  gap: 2px;
  margin: 0 0 18px 0;
  border-bottom: 1px solid var(--rule);
  padding: 0;
}
.tabs .tab {
  display: inline-block;
  padding: 9px 20px;
  font-size: 14px;
  letter-spacing: 0.01em;
  color: var(--ink-muted);
  text-decoration: none;
  border: 1px solid transparent;
  border-bottom: none;
  border-radius: 5px 5px 0 0;
  margin-bottom: -1px;
  background: transparent;
}
.tabs .tab:hover { color: var(--ink); background: var(--surface-sunken); }
.tabs .tab-active {
  color: var(--ink);
  background: var(--surface-raised);
  border-color: var(--rule);
  border-bottom: 1px solid var(--surface-raised);
  font-weight: 600;
  box-shadow: inset 0 2px 0 var(--accent-blue-in);
}
.tabs .tab-disabled { color: var(--rule); cursor: default; }
.tabs .tab-disabled:hover { background: transparent; color: var(--rule); }

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
/* THE PANEL IS HIDDEN BY A CLASS ON `body`, NOT ON ITSELF. That is what lets one class change
   swap both controls at once without the server re-rendering either of them. */
body.panel-collapsed .panel { display: none; }
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
/* Always rendered, shown only when the panel is away. Hiding it in CSS rather than omitting it
   from the markup is what makes reopening free. */
.reopen { display: none; margin-bottom: .8rem; padding: .2rem .55rem;
          border: 1px solid var(--rule); border-radius: 5px; background: var(--surface-raised);
          text-decoration: none; color: var(--ink); }
body.panel-collapsed .reopen { display: inline-block; }

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

/* The one figure on the model-comparison page a reviewer must not be able to miss: source ranges
   a parse never mentioned in any form. Weight and size only — the badge already says SILENTLY
   OMITTED in words, because status is never carried by colour alone. */
td.omitted { font-weight: 700; white-space: nowrap; }
td.omitted .badge { font-size: .8rem; padding: .12rem .5rem; }

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

/* --- the assembled parse ---------------------------------------------------------------------
   A NESTED NODE IS INDENTED BY ITS OWN RULE AND NOT BY A MARGIN ON `.node`. The nesting is the
   model's `parent_id` chain, so depth is whatever the model declared; a fixed indent per level
   compounds correctly at any depth without the renderer counting one. */
.node .node { margin-left: .6rem; }

/* A PART IS COLLAPSED MARKUP, NOT A SCRIPTED WIDGET. `details` works with scripting disabled, is
   keyboard operable, and a browser's find-in-page opens it — which matters on a page whose whole
   purpose is locating one disclosure among 81 parts. */
details.part { border: 1px solid var(--rule); border-radius: 6px; margin: .5rem 0;
               padding: .35rem .6rem; }
details.part > summary { cursor: pointer; padding: .15rem 0; }
details.part > summary .title { font-weight: 600; }
details.part[open] > summary { border-bottom: 1px solid var(--rule); margin-bottom: .4rem; }

/* The jump index. Two columns so 81 parts are a map rather than another scroll. */
.part-index { columns: 2; column-gap: 1.2rem; margin: .5rem 0 .8rem; padding: 0; list-style: none; }
.part-index li { break-inside: avoid; }

/* --- comparing two parses of one filing ------------------------------------------------------
   FOUR PANES, EACH SCROLLING INDEPENDENTLY. The preserved bytes are identical on both rows — every
   run of one accession carries the same source_set_id — so the second source pane exists for its
   SCROLL POSITION, not its content: a reviewer parks each one at the passage its own parse is
   discussing. A single shared pane would force both comparisons to the same offset, which is the
   one position they are never both interesting at. */
.compare-row { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem;
               border-top: 2px solid var(--rule); padding-top: .5rem; margin-top: .6rem; }
.compare-row > .compare-head { grid-column: 1 / -1; }
.compare-head h2 { margin: 0; }
.compare-source, .compare-parsed { max-height: 70vh; overflow: auto;
                                   border: 1px solid var(--rule); border-radius: 6px;
                                   padding: .4rem .6rem; }
/* The panes stack on a narrow viewport rather than scrolling the page sideways. */
@media (max-width: 1100px) { .compare-row { grid-template-columns: 1fr; } }

.compare-chooser { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap;
                   margin: .6rem 0; }
.compare-chooser select { padding: .3rem; max-width: 26rem; }

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

/* --- global nav, panel modes, and the contextual review menu -------------------------------
   THREE SIGNALS FOR ACTIVE, NEVER COLOUR ALONE: aria-current, a filled surface, and a leading
   glyph rendered in the markup. The same rule the tab strip above already follows, and the reason
   every status marker in this stylesheet has a text equivalent. */
.panel-nav ul { list-style: none; margin: 0 0 .5rem; padding: 0; }
.panel-nav a.nav-item { display: block; padding: .3rem .45rem; border-radius: 5px;
                        border: 1px solid transparent; color: var(--panel-text);
                        text-decoration: none; }
.panel-nav a.nav-item:hover { background: #33383e; }
.panel-nav a.nav-active { background: #2f343a; border-color: #5a616a; font-weight: 600; }
.panel-nav .hint { display: block; margin: 0 0 .35rem .95rem; }

.panel-mode { display: flex; flex-wrap: wrap; gap: .3rem; align-items: baseline;
              border-top: 1px solid #4e545b; border-bottom: 1px solid #4e545b;
              padding: .45rem 0; margin: .45rem 0 .6rem; }
.panel-mode .mode { padding: .18rem .5rem; border-radius: 5px; border: 1px solid #4e545b;
                    color: var(--panel-text); text-decoration: none; font-size: .78rem; }
.panel-mode .mode-active { background: #2f343a; border-color: #5a616a; font-weight: 600; }
.panel-mode .mode-disabled { opacity: .55; cursor: default; }

.panel-section { border-top: 1px solid #4e545b; margin-top: .7rem; padding-top: .5rem; }
.panel-section h2 { font-size: .72rem; text-transform: uppercase; letter-spacing: .07em;
                    color: var(--panel-muted); margin: 0 0 .35rem; }
.panel-section a { color: #cfe0f7; text-decoration: none; display: inline-block; }
.panel-section .step-disabled { color: var(--panel-muted); cursor: default; }
.panel ol.steps, .panel ul.menu { list-style: none; margin: 0; padding: 0; }
.panel ol.steps > li { margin: .32rem 0; font-size: .8rem; }
.panel ol.steps > li[aria-current="step"] { background: #2f343a; border-radius: 5px;
                                            padding: .2rem .35rem; font-weight: 600; }
.panel ul.menu > li { margin: .28rem 0; font-size: .8rem; }

/* --- breadcrumbs -------------------------------------------------------------------------- */
.crumbs { display: flex; flex-wrap: wrap; gap: .3rem; align-items: baseline;
          font-size: .78rem; color: var(--ink-muted); margin: 0 0 .55rem; }
.crumbs a { text-decoration: none; }
.crumbs .sep { color: var(--rule); }
.crumbs [aria-current="page"] { color: var(--ink); font-weight: 600; }

/* --- what a link will do, before it is clicked ---------------------------------------------
   A tooltip is not one of these. `title` does not exist on touch and is invisible to a keyboard,
   so every one of these markers is text that is always on the page. */
.scope, .kind-word { display: inline-block; border: 1px solid var(--rule); border-radius: 4px;
                     padding: 0 .3rem; font-size: .7rem; text-transform: uppercase;
                     letter-spacing: .05em; color: var(--ink-muted); }
.panel .scope, .panel .kind-word { border-color: #5a616a; color: var(--panel-muted); }

/* --- opened markers. Three words, never two, and never a bare glyph. -----------------------
   `opened` means this server rendered that page at the version stated. It is not a review and
   not a judgement, which is why none of these classes may ever carry a tick on its own. */
.opened, .opened-earlier, .opened-never { font-size: .72rem; white-space: nowrap; }
.opened          { color: var(--ink-muted); }
.opened-earlier  { color: var(--ink); background: var(--accent-amber);
                   border-radius: 4px; padding: 0 .3rem; }
.opened-never    { color: var(--ink-muted); }
.panel .opened, .panel .opened-never { color: var(--panel-muted); }

/* --- the hub ------------------------------------------------------------------------------ */
.steps-table td { vertical-align: top; }
.steps-table td.where { white-space: normal; }
.steps-table .mono { display: block; word-break: break-all; }
.tiles { display: flex; flex-wrap: wrap; gap: .6rem; margin: .3rem 0; }
.tiles .tile { flex: 1 1 15rem; min-width: 0; border: 1px solid var(--rule); border-radius: 8px;
               padding: .55rem .7rem; background: var(--surface-raised); }
.tiles .tile h3 { margin: 0 0 .25rem; }

/* --- the hierarchy filter strip. Narrows; never reorders. ---------------------------------
   A list that reorders by a computed figure is a ranking, and a stable position is the only
   thing that makes "where was I" answerable across 77 rows. */
.filters { display: flex; flex-wrap: wrap; gap: .35rem; margin: .3rem 0 .6rem; }
.filters a, .filters span { font-size: .76rem; padding: .12rem .45rem; border-radius: 5px;
                            border: 1px solid var(--rule); text-decoration: none; }
.filters .filter-active { background: var(--surface-sunken); font-weight: 600; }
"""

SCRIPT: Final[str] = """
// The only script in the application. It copies the run identifier and it collapses the panel.
//
// Everything that matters here works with scripting disabled: the raw and parsed views, the
// side-by-side view, source-reference navigation, comments and review actions are ordinary links
// and form posts rendered by the server. That is not nostalgia — it means the review surface has
// no client-side state to lose, no rendering path that can disagree with what was stored, and no
// way for a preserved filing to reach a JavaScript context at all.
//
// THE PANEL TOGGLE IS AN ENHANCEMENT, NOT A MECHANISM. Both controls are real links to
// `?panel=open` and `?panel=closed` and still work with scripting off; this only spares the round
// trip. It writes a cookie so the SERVER renders the right mode on the next page, which is what
// makes the choice survive navigation — a query parameter was lost the moment you clicked a link,
// so the panel silently reappeared on every page.
(function () {
  "use strict";
  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-panel]");
    if (toggle) {
      event.preventDefault();
      var closed = toggle.getAttribute("data-panel") === "closed";
      document.body.classList.toggle("panel-collapsed", closed);
      document.cookie =
        "kopexx_panel=" + (closed ? "closed" : "open") +
        "; Path=/; Max-Age=31536000; SameSite=Strict";
      return;
    }
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
