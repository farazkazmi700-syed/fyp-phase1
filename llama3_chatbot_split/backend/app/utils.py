import json
import uuid
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse, urljoin
from flask import request, session, jsonify, redirect, url_for
from .database import get_db


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def json_payload() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def current_user_id() -> str | None:
    return session.get("user_id")


def current_user() -> dict:
    return {
        "id": session.get("user_id", ""),
        "name": session.get("username", "User"),
        "email": session.get("email", ""),
        "picture": session.get("picture_url", ""),
    }


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            if request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)
    return wrapper


def log_analytics(user_id: str, event_type: str, metadata: dict = None):
    db = get_db()
    db.execute(
        "INSERT INTO analytics (id, user_id, event_type, metadata, created_at) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), user_id, event_type, json.dumps(metadata or {}), now_iso())
    )
    db.commit()


def safe_redirect_target(target: str | None) -> str:
    if not target:
        return url_for("chat.chat_page")
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    if redirect_url.scheme in ("http", "https") and redirect_url.netloc == host_url.netloc:
        return redirect_url.geturl()
    return url_for("chat.chat_page")
