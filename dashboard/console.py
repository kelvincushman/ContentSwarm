"""Same-origin browser session and mobile console; credentials never enter JS."""

import hmac
import os
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from flask import jsonify, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix


def transport_allowed():
    return request.is_secure or urlsplit(request.host_url).hostname in ("127.0.0.1", "::1", "localhost")


def install_console(app):
    if not os.environ.get("CONTENTSWARM_API_TOKEN"):
        raise RuntimeError("CONTENTSWARM_API_TOKEN is required; load it from your keyring or service environment before starting ContentSwarm")
    if os.environ.get("CONTENTSWARM_CONSOLE_TOKEN") == os.environ["CONTENTSWARM_API_TOKEN"]:
        raise RuntimeError("CONTENTSWARM_CONSOLE_TOKEN must differ from the agent API token")
    loopbacks = ("127.0.0.1", "::1", "localhost")
    if os.environ.get("CONTENTSWARM_HOST", "127.0.0.1") not in loopbacks:
        raise RuntimeError("Bind ContentSwarm to loopback; use a local HTTPS reverse proxy or an encrypted tunnel for remote access")
    if os.environ.get("CONTENTSWARM_TRUST_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0, x_port=0, x_prefix=0)
    secure_cookie = os.environ.get("CONTENTSWARM_COOKIE_SECURE", "1") != "0"
    if not secure_cookie and os.environ.get("CONTENTSWARM_HOST", "127.0.0.1") not in loopbacks:
        raise RuntimeError("CONTENTSWARM_COOKIE_SECURE=0 is only supported with a loopback CONTENTSWARM_HOST")
    app.secret_key = secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=secure_cookie,
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=1024 * 1024)

    @app.before_request
    def protect_dashboard():
        if request.path == "/" or request.path.startswith("/static/"):
            return None
        if request.path.startswith("/api/") or request.path.startswith("/generated/"):
            if not transport_allowed():
                return jsonify(error="HTTPS is required for remote access"), 403
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                return jsonify(error="Cross-origin request refused"), 403
            token = os.environ.get("CONTENTSWARM_API_TOKEN", "")
            bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if token and hmac.compare_digest(bearer.encode("utf-8", "surrogatepass"), token.encode("utf-8", "surrogatepass")):
                return None
            if request.path == "/api/console/login":
                return None
            if session.get("console"):
                if request.method not in ("GET", "HEAD") and not hmac.compare_digest(request.headers.get("X-CSRF-Token", "").encode("utf-8", "surrogatepass"), session.get("csrf", "!").encode("utf-8", "surrogatepass")):
                    return jsonify(error="Invalid CSRF token"), 403
                return None
            return jsonify(error="Sign in to ContentSwarm"), 401

    @app.post("/api/console/login")
    def login():
        data = request.get_json(silent=True) or {}
        token = os.environ.get("CONTENTSWARM_CONSOLE_TOKEN", "")
        supplied = data.get("token") if isinstance(data, dict) else None
        if not token or not isinstance(supplied, str) or not hmac.compare_digest(token.encode("utf-8", "surrogatepass"), supplied.encode("utf-8", "surrogatepass")):
            return jsonify(error="Invalid console token or console login not configured"), 401
        session.clear()
        session.permanent = True
        session.update(console=True, csrf=secrets.token_hex(32))
        return jsonify(csrf=session["csrf"])

    @app.get("/api/console/session")
    def current_session():
        return jsonify(csrf=session.get("csrf"))

    @app.post("/api/console/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    app.view_functions["index"] = lambda: render_template("console.html")
