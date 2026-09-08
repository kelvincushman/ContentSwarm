"""Same-origin browser session and mobile console; credentials never enter JS."""

import hmac
import os
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from flask import jsonify, render_template, request, session


def install_console(app):
    app.secret_key = secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=1024 * 1024)

    @app.before_request
    def protect_dashboard():
        if request.path == "/" or request.path.startswith("/static/"):
            return None
        if request.path.startswith("/api/") or request.path.startswith("/generated/"):
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                return jsonify(error="Cross-origin request refused"), 403
            token = os.environ.get("CONTENTSWARM_API_TOKEN", "")
            bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if token and hmac.compare_digest(bearer, token):
                return None
            if request.path == "/api/console/login":
                return None
            if session.get("console"):
                if request.method not in ("GET", "HEAD") and not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("csrf", "!")):
                    return jsonify(error="Invalid CSRF token"), 403
                return None
            return jsonify(error="Sign in to ContentSwarm"), 401

    @app.post("/api/console/login")
    def login():
        data = request.get_json(silent=True) or {}
        token = os.environ.get("CONTENTSWARM_API_TOKEN", "")
        supplied = data.get("token") if isinstance(data, dict) else None
        if not token or not isinstance(supplied, str) or not hmac.compare_digest(token, supplied):
            return jsonify(error="Invalid token or server token not configured"), 401
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
