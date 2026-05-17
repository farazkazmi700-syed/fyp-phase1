import os
import uuid
import requests
from flask import Blueprint, render_template, request, redirect, url_for, session
from google_auth_oauthlib.flow import Flow
from .config import Config, BASE_DIR, PROJECT_DIR
from .database import get_db
from .utils import now_iso, current_user_id, safe_redirect_target, log_analytics

auth_bp = Blueprint("auth", __name__)


def oauth_redirect_uri() -> str:
    return Config.GOOGLE_REDIRECT_URI or url_for("auth.auth_callback", _external=True)


def google_credentials_path() -> str | None:
    candidates = [
        os.path.join(BASE_DIR, "credentials.json"),
        os.path.join(PROJECT_DIR, "credentials.json"),
    ]
    return next((path for path in candidates if os.path.exists(path)), None)


def get_google_oauth_flow():
    redirect_uri = oauth_redirect_uri()
    credentials_path = google_credentials_path()
    if credentials_path:
        return Flow.from_client_secrets_file(
            credentials_path,
            scopes=Config.SCOPES,
            redirect_uri=redirect_uri,
            autogenerate_code_verifier=False,
        )

    if not Config.GOOGLE_CLIENT_ID or not Config.GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )

    client_config = {
        "web": {
            "client_id": Config.GOOGLE_CLIENT_ID,
            "client_secret": Config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=Config.SCOPES,
        redirect_uri=redirect_uri,
        autogenerate_code_verifier=False,
    )


@auth_bp.route("/")
def index():
    if current_user_id():
        return redirect(url_for("chat.chat_page"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login")
def login():
    if current_user_id():
        return redirect(url_for("chat.chat_page"))
    return render_template("login.html")


@auth_bp.route("/auth/login")
@auth_bp.route("/auth/google")
def auth_login():
    try:
        flow = get_google_oauth_flow()
        session["post_auth_redirect"] = safe_redirect_target(request.args.get("next") or url_for("chat.chat_page"))
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        session["oauth_state"] = state
        return redirect(authorization_url)
    except Exception as e:
        return render_template("login.html", error=f"OAuth initialization failed: {str(e)}")


@auth_bp.route("/auth/callback")
def auth_callback():
    try:
        code = request.args.get("code")
        if not code:
            return render_template("login.html", error="Authorization failed.")

        flow = get_google_oauth_flow()
        flow.oauth2session.state = session.get("oauth_state")
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials

        user_info_response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=20,
        )
        user_info_response.raise_for_status()
        user_info = user_info_response.json()

        google_id = user_info["id"]
        email = user_info["email"]
        name = user_info.get("name", "")
        picture_url = user_info.get("picture", "")

        db = get_db()
        user = db.execute("SELECT id FROM users WHERE google_id = ?", (google_id,)).fetchone()
        if user:
            user_id = user["id"]
        else:
            user_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO users (id, google_id, email, name, picture_url, created_at) VALUES (?,?,?,?,?,?)",
                (user_id, google_id, email, name, picture_url, now_iso())
            )
            db.commit()
            log_analytics(user_id, "google_signup")

        redirect_target = session.pop("post_auth_redirect", url_for("chat.chat_page"))
        session.clear()
        session["user_id"] = user_id
        session["username"] = name
        session["email"] = email
        session["picture_url"] = picture_url
        log_analytics(user_id, "login")

        return redirect(redirect_target)
    except Exception as e:
        return render_template("login.html", error=f"Authentication failed: {str(e)}")


@auth_bp.route("/logout")
@auth_bp.route("/auth/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
