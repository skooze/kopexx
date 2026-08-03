"""HTML construction with escaping that is not optional.

SECURITY-INVARIANT: EVERY value that reaches a page goes through `esc`. Two of the sources feeding
this UI are untrusted in the strongest sense — the preserved bytes of an SEC filing, and the text a
language model returned after reading one. rules.md section 11 and the UX specification both say
the same thing: filing text is untrusted data, model output is data and is rendered as text, and
neither is ever evaluated or injected as markup.

    A FILING IS NEVER RENDERED AS MARKUP. Raw source is shown as escaped text inside a preformatted
    block. There is no sanitizer to get wrong and no sandboxed iframe to configure, because nothing
    from a filing is ever parsed as HTML by the browser at all. That is also why the content
    security policy can be as strict as it is.

`raw` EXISTS FOR MARKUP THIS MODULE BUILT AND FOR NOTHING ELSE. It is not an escape hatch for a
value that "looks safe": the two callers that use it pass strings assembled here, from other
escaped pieces.
"""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote, urlencode


def esc(value: Any) -> str:
    """Escape any value for HTML text or an attribute. Quotes included."""
    return escape(str(value), quote=True)


def url(*parts: Any, **query: Any) -> str:
    """Build a URL whose components are PERCENT-encoded, not HTML-escaped.

    THESE ARE DIFFERENT ENCODINGS AND CONFUSING THEM PRODUCES A WRONG LINK. `esc` is HTML escaping;
    a value containing `&`, `?`, `#` or a space needs percent-encoding to survive a query string,
    and running it through `esc` first and then through `attributes` escapes it twice — a run
    identifier `run&1` became `href="/runs/run&amp;amp;1"`, which a browser resolves to
    `/runs/run&amp;1`. It was masked only because identifiers are generated and SEC filenames are
    conservative, which is the kind of masking that ends the moment a real filename is not.

    Components are percent-encoded here; `attributes` applies the single HTML escape.
    """

    # `x not in (None, "", False)` WOULD DROP A ZERO, because `0 == False` in Python. A source
    # reference resolving at offset 0 — the first character of a filing, which is exactly where a
    # cover page starts — would lose its offset and the raw view would highlight nothing. The
    # emptiness test is therefore explicit about which kinds of empty it means.
    def present(value: Any) -> bool:
        if value is None or value is False:
            return False
        return not (isinstance(value, str) and not value)

    path = "/".join(quote(str(part), safe="") for part in parts if present(part))
    joined = "/" + path if parts else ""
    pairs = [(key, str(value)) for key, value in query.items() if present(value)]
    if not pairs:
        return joined
    return joined + "?" + urlencode(pairs)


def attributes(**pairs: Any) -> str:
    """Render attributes, dropping any whose value is None or False."""
    parts = []
    for key, value in pairs.items():
        if value is None or value is False:
            continue
        name = key.rstrip("_").replace("_", "-")
        if value is True:
            parts.append(name)
        else:
            parts.append(f'{name}="{esc(value)}"')
    return (" " + " ".join(parts)) if parts else ""


def tag(element: str, content: str = "", /, **pairs: Any) -> str:
    """One element. `content` is markup this module produced; values are escaped by the caller.

    The two leading parameters are POSITIONAL-ONLY. Without that, `tag("input", "", name="cik")`
    collides with the parameter that names the element — and an HTML `name` attribute is one of the
    most common things a form needs to set.
    """
    return f"<{element}{attributes(**pairs)}>{content}</{element}>"


def void(element: str, /, **pairs: Any) -> str:
    return f"<{element}{attributes(**pairs)}>"


def join(*parts: str) -> str:
    return "".join(p for p in parts if p)


def each(items: Any, render: Any) -> str:
    return "".join(render(item) for item in items)


def badge(label: str, kind: str = "neutral") -> str:
    return tag("span", esc(label), class_=f"badge badge-{kind}")


def warning(message: str) -> str:
    """A warning shown at the point of use. A warning nobody sees protects nobody."""
    return tag("p", esc(message), class_="warning", role="status")
