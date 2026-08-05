"""Local security for the review application: loopback by default, authenticated beyond it.

THE THREAT THIS ADDRESSES. The review UI reads preserved SEC filings, shows run evidence, and has
a button that spends money against a real AWS account. On loopback that is a single-user developer
tool. On a LAN it is an unauthenticated remote-control for someone else's bill.

WHAT IS ENFORCED, AND WHERE.

    BIND ADDRESS        `packages/configuration.ReviewSettings` refuses to construct a non-loopback
                        configuration without a development secret. The unsafe combination is not
                        reachable by forgetting a flag.
    SESSION             a server-side session, keyed by a random cookie value. The cookie carries
                        an opaque identifier and nothing else — no role, no user record, no signed
                        claim a client could forge or replay after a restart.
    CSRF                every state-changing request carries a token bound to the session. A
                        browser on another origin can make the request; it cannot read the token.
    SAME ORIGIN         no CORS headers are emitted at all. The absence is the policy: a browser
                        refuses a cross-origin read without them, and adding a permissive header
                        "for development" is how one reaches production.
    CREDENTIALS         nothing AWS-shaped is ever placed in a response. All model access is
                        server-side, and there is no browser-to-Bedrock path to accidentally open.

WHAT THIS IS NOT. It is not multi-user identity management, and it does not pretend to be. ADR-0014
defers that; roadmap.md Phase 6 requires exactly this minimum before binding beyond loopback, and
the UI labels itself local development mode whenever HTTPS is not configured, rather than implying
a security posture it does not have.
"""

from __future__ import annotations

import hmac
import secrets
import threading
from dataclasses import dataclass
from typing import Final

from .router import Request, Response, as_json

SESSION_COOKIE: Final[str] = "kopexx_review_session"
CSRF_FIELD: Final[str] = "csrf_token"
CSRF_HEADER: Final[str] = "x-csrf-token"

#: Sent on every response. `default-src 'none'` means a page can load nothing it was not told to,
#: and the review UI is told to load exactly one stylesheet and one script from its own origin.
#: Raw filings are rendered as ESCAPED TEXT, never as markup, so no filing can execute anything —
#: which is why `script-src 'self'` is safe here and why no sandboxed iframe is needed.
SECURITY_HEADERS: Final[dict[str, str]] = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'self'; script-src 'self'; img-src 'none'; "
        "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}


@dataclass
class Session:
    """One authenticated browser session, held server-side."""

    session_id: str
    csrf_token: str


class SessionStore:
    """In-memory sessions. Deliberately not durable.

    A restart logs everybody out, which for a single-user local tool is correct: sessions that
    survive a restart are sessions that survive a compromise, and there is nothing here worth the
    persistence machinery.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self) -> Session:
        session = Session(
            session_id=secrets.token_urlsafe(32), csrf_token=secrets.token_urlsafe(32)
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


def cookie_value(request: Request, name: str) -> str:
    """One cookie value, parsed without a cookie library."""
    for part in request.header("cookie").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def set_cookie(session_id: str, *, https: bool) -> str:
    """The session cookie.

    `Secure` is set only when HTTPS is actually configured. Setting it over plain HTTP makes the
    browser discard the cookie, which produces a login loop that looks like a bug rather than the
    security control it was meant to be — so the mode is stated honestly instead.
    """
    attributes = [
        f"{SESSION_COOKIE}={session_id}",
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
    ]
    if https:
        attributes.append("Secure")
    return "; ".join(attributes)


class SecurityPolicy:
    """Whether a request is allowed through, and what it must carry."""

    def __init__(
        self,
        *,
        loopback_only: bool,
        dev_auth_secret: str | None,
        sessions: SessionStore | None = None,
        https: bool = False,
        allowed_hosts: frozenset[str] = frozenset(),
        authentication_disabled: bool = False,
    ) -> None:
        self.loopback_only = loopback_only
        self._secret = dev_auth_secret
        self.sessions = sessions or SessionStore()
        self.https = https
        self.authentication_disabled = authentication_disabled
        self.allowed_hosts = frozenset(h.strip().lower() for h in allowed_hosts if h.strip())

    def check_host(self, request: Request) -> Response | None:
        """None when the request names a permitted host, or the response that refuses it.

        WHAT THIS DEFENDS AGAINST, AND WHY A REVERSE PROXY DOES NOT ALREADY DO IT. When this
        application is published under a name, TLS is terminated in front of it and the application
        itself still listens on a raw port that anything on the network can reach directly. A
        request that arrives by IP address, or under some other name pointed at the same address,
        has bypassed the proxy entirely — and with it every rule the proxy was configured to apply.
        Checking the name HERE is what makes the published name the only way in.

        IT ALSO CLOSES DNS REBINDING. A page on an attacker's origin can point its own hostname at
        this address and have the victim's browser issue requests that carry the victim's cookies.
        `SameSite=Strict` and the CSRF token already make that hard; refusing an unrecognised Host
        makes it not start.

        THE PORT IS STRIPPED BEFORE COMPARISON because a browser includes it when it is not the
        scheme default, so `kopexx.com` and `kopexx.com:8765` are the same name. An IPv6 literal
        keeps its brackets, which is what distinguishes its colons from a port separator.

        AN EMPTY ALLOW-LIST DISABLES THE CHECK. That is the configuration every loopback-only
        developer instance has, where there is no published name to enforce and the interface
        binding is already the control.
        """
        if not self.allowed_hosts:
            return None
        raw = request.header("host").strip().lower()
        name = raw
        if name.startswith("["):
            name = name[: name.index("]") + 1] if "]" in name else name
        elif ":" in name:
            name = name.rsplit(":", 1)[0]
        if name in self.allowed_hosts:
            return None
        return as_json(
            {
                "code": "host_not_permitted",
                "message": (
                    "this instance answers only to the host names it was configured with. Reach "
                    "it by its published name rather than by address."
                ),
            },
            status=421,
        )

    @property
    def authentication_required(self) -> bool:
        """Loopback-only needs none, and neither does an instance published without it on purpose.

        `authentication_disabled` reaches here only from `REVIEW_PUBLIC_UNAUTHENTICATED`, which the
        settings refuse to infer. Everything else that binds beyond loopback still requires the
        secret, because the settings guarantee one exists.
        """
        return not self.loopback_only and not self.authentication_disabled

    def check_secret(self, supplied: str) -> bool:
        """Constant-time comparison. A timing oracle on a short secret is a real oracle."""
        if not self._secret:
            return False
        return hmac.compare_digest(supplied, self._secret)

    def session_for(self, request: Request) -> Session | None:
        return self.sessions.get(cookie_value(request, SESSION_COOKIE))

    def authorize(self, request: Request) -> Response | None:
        """None when the request may proceed, or the response that refuses it."""
        if not self.authentication_required:
            return None
        if self.session_for(request) is not None:
            return None
        if request.wants_html():
            return Response(status=303, body=b"", headers={"Location": "/sign-in"})
        return as_json(
            {
                "code": "authentication_required",
                "message": (
                    "this instance is bound beyond the loopback interface and requires the "
                    "development authentication secret"
                ),
            },
            status=401,
        )

    def check_csrf(self, request: Request) -> Response | None:
        """None when a state-changing request is permitted, or the response that refuses it.

        On loopback with no session there is no token to bind to and no cross-origin browser
        session to protect; the check applies wherever a session exists, which is every
        configuration that binds beyond loopback.
        """
        session = self.session_for(request)
        if session is None:
            return None if not self.authentication_required else self.authorize(request)
        supplied = request.header(CSRF_HEADER) or request.form().get(CSRF_FIELD, "")
        if hmac.compare_digest(supplied, session.csrf_token):
            return None
        return as_json(
            {"code": "csrf_failed", "message": "the request carried no valid CSRF token"},
            status=403,
        )

    def decorate(self, response: Response) -> Response:
        """Apply the security headers to every response, without exception."""
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response
