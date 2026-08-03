"""The parser-review HTTP application: routes, security, and the server that serves them.

Built on the standard library on purpose. Twenty routes, two assets and one event stream, served to
one developer on loopback, do not justify a web framework, an ASGI server and a build step —
rules.md prohibits a large framework without need, and the runtime dependency list is two packages.

Every handler is a function from a request to a response, so the whole API is exercised without
opening a socket. The browser never receives a credential, a provider endpoint or a filesystem
path, and there is no browser-to-Bedrock route.
"""

from .app import Application, build, build_provider, serve
from .handlers import ReviewApp
from .router import Request, Response, Route, Router, as_json, html, redirect, text
from .security import (
    CSRF_FIELD,
    CSRF_HEADER,
    SECURITY_HEADERS,
    SESSION_COOKIE,
    SecurityPolicy,
    Session,
    SessionStore,
    cookie_value,
    set_cookie,
)
from .server import MAX_REQUEST_BYTES, ReviewServer, build_request

__all__ = [
    "CSRF_FIELD",
    "CSRF_HEADER",
    "MAX_REQUEST_BYTES",
    "SECURITY_HEADERS",
    "SESSION_COOKIE",
    "Application",
    "Request",
    "Response",
    "ReviewApp",
    "ReviewServer",
    "Route",
    "Router",
    "SecurityPolicy",
    "Session",
    "SessionStore",
    "as_json",
    "build",
    "build_provider",
    "build_request",
    "cookie_value",
    "html",
    "redirect",
    "serve",
    "set_cookie",
    "text",
]
