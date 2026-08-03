"""A small request/response model and a path router. No framework, and that is deliberate.

WHY NOT A WEB FRAMEWORK. rules.md prohibits introducing a large framework without need, and the
repository's whole runtime dependency list is two packages. What this application needs is a dozen
routes, a static asset or two, and one server-sent-event stream, served to one developer on
loopback. `http.server` already does that. Adding a framework and an ASGI server would be three
new dependencies, a supply-chain surface and a `pip-audit` obligation bought for routing.

WHY HANDLERS ARE PURE FUNCTIONS OF A REQUEST. Every handler here takes a `Request` and returns a
`Response`. That means the entire API is exercised in the test suite without opening a socket,
which keeps the suite free of ports, timeouts and flakes, and keeps `test-no-skips` honest — a
test that needs a listening server is a test that will eventually skip somewhere.

STREAMING IS THE ONE EXCEPTION. A server-sent-event response cannot be a finished string, so it
carries an iterator instead of a body. Everything else about it is an ordinary response.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

#: A path segment placeholder: `/runs/{run_id}/jobs/{job_id}`.
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class Request:
    """One inbound HTTP request, already parsed and already bounded."""

    method: str
    path: str
    query: dict[str, list[str]] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    params: dict[str, str] = field(default_factory=dict)
    client_host: str = ""

    def q(self, name: str, default: str = "") -> str:
        values = self.query.get(name) or []
        return values[0] if values else default

    def header(self, name: str, default: str = "") -> str:
        return self.headers.get(name.lower(), default)

    def form(self) -> dict[str, str]:
        """Parse an `application/x-www-form-urlencoded` body into single values."""
        parsed = parse_qs(self.body.decode("utf-8", errors="replace"), keep_blank_values=True)
        return {key: values[0] for key, values in parsed.items() if values}

    def json_body(self) -> Any:
        """Parse a JSON body. Browser-facing JSON is outside the model content boundary."""
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))

    def wants_html(self) -> bool:
        return "text/html" in self.header("accept", "")


@dataclass
class Response:
    """One outbound HTTP response. `stream` replaces `body` for server-sent events."""

    status: int = 200
    body: bytes = b""
    content_type: str = "text/html; charset=utf-8"
    headers: dict[str, str] = field(default_factory=dict)
    stream: Iterator[bytes] | None = None


def html(markup: str, *, status: int = 200, headers: dict[str, str] | None = None) -> Response:
    return Response(
        status=status,
        body=markup.encode("utf-8"),
        content_type="text/html; charset=utf-8",
        headers=headers or {},
    )


def as_json(payload: Any, *, status: int = 200) -> Response:
    """A browser-facing JSON response.

    JSON IS CORRECT HERE AND IS NOT A BOUNDARY VIOLATION. ADR-0013 governs MODEL-visible content;
    a browser is not a model, and `docs/api/openapi.yaml` has described this API as JSON since
    before any of it existed.
    """
    return Response(
        status=status,
        body=json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"),
        content_type="application/json; charset=utf-8",
    )


def text(
    body: str, *, status: int = 200, content_type: str = "text/plain; charset=utf-8"
) -> Response:
    return Response(status=status, body=body.encode("utf-8"), content_type=content_type)


def redirect(location: str) -> Response:
    return Response(status=303, body=b"", headers={"Location": location})


Handler = Callable[[Request], Response]


class Route:
    """One method and path pattern, compiled once."""

    def __init__(self, method: str, pattern: str, handler: Handler, *, name: str) -> None:
        self.method = method.upper()
        self.pattern = pattern
        self.name = name
        self.handler = handler
        self.regex = re.compile(
            "^" + _PLACEHOLDER.sub(lambda m: f"(?P<{m.group(1)}>[^/]+)", pattern) + "$"
        )

    def match(self, path: str) -> dict[str, str] | None:
        found = self.regex.match(path)
        return found.groupdict() if found else None


class Router:
    """The route table. Also the source of truth the OpenAPI contract test compares against."""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, pattern: str, handler: Handler, *, name: str) -> None:
        self._routes.append(Route(method, pattern, handler, name=name))

    def get(self, pattern: str, *, name: str) -> Callable[[Handler], Handler]:
        def register(handler: Handler) -> Handler:
            self.add("GET", pattern, handler, name=name)
            return handler

        return register

    def post(self, pattern: str, *, name: str) -> Callable[[Handler], Handler]:
        def register(handler: Handler) -> Handler:
            self.add("POST", pattern, handler, name=name)
            return handler

        return register

    @property
    def routes(self) -> tuple[Route, ...]:
        return tuple(self._routes)

    def implemented(self) -> tuple[tuple[str, str], ...]:
        """(METHOD, path) for every route this application actually serves.

        `tests/architecture/test_openapi_contract.py` reads this and fails if the specification
        and the application disagree in either direction. A contract that documents an endpoint
        nobody built, or omits one somebody did, is a contract that has stopped describing the
        system.
        """
        return tuple(sorted({(r.method, r.pattern) for r in self._routes}))

    def resolve(self, method: str, path: str) -> tuple[Handler, dict[str, str]] | None:
        permitted: list[str] = []
        for route in self._routes:
            params = route.match(path)
            if params is None:
                continue
            if route.method != method.upper():
                permitted.append(route.method)
                continue
            return route.handler, params
        if permitted:
            # RFC 9110 section 15.5.6 requires an `Allow` header on a 405, and the route table
            # already knows the answer. A 405 without it tells a client it guessed wrong and
            # refuses to say what would have been right.
            allow = ", ".join(sorted(set(permitted)))
            return (lambda request: _method_not_allowed(request, allow)), {}
        return None


def _method_not_allowed(request: Request, allow: str = "") -> Response:
    response = as_json(
        {
            "code": "method_not_allowed",
            "message": f"{request.method} is not allowed here",
            "allow": allow,
        },
        status=405,
    )
    if allow:
        response.headers["Allow"] = allow
    return response
