"""
app.py - Main Flask Application Entry Point
Multi-Turn AI Chatbot with LLaMA 3 via Groq API
Architecture: FR1 (System Initialization) bootstraps all modules
"""

import os
import sqlite3
import json
import uuid
import requests
from collections import Counter
from datetime import datetime
from tempfile import gettempdir
from urllib.parse import quote, urlparse, urljoin
from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, g
)
from flask_cors import CORS
from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

# ─────────────────────────────────────────────
# FR1: SYSTEM INITIALIZATION
# Load environment variables and configure app
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
load_dotenv(os.path.join(PROJECT_DIR, ".env"))
load_dotenv(os.path.join(BASE_DIR, ".env"))
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
CORS(app, supports_credentials=True)

# ── Groq API config (LLaMA 3 model) ──────────
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "").strip()
GROQ_API_URL  = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
LLAMA_MODEL   = os.getenv("GROQ_MODEL") or os.getenv("LLAMA_MODEL") or "llama-3.1-8b-instant"
default_database_path = os.path.join(gettempdir(), "chatbot.db") if os.getenv("VERCEL") else os.path.join(BASE_DIR, "chatbot.db")
DATABASE_PATH = os.getenv("DATABASE_PATH") or default_database_path
if not os.path.isabs(DATABASE_PATH):
    DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_PATH)
APP_PORT = int(os.getenv("APP_PORT", "5000"))

# ── Google OAuth 2.0 config ─────────────────
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]


# ─────────────────────────────────────────────
# DATABASE LAYER  (FR3 – Data Storage Operations)
# SQLite connection lifecycle tied to request
# ─────────────────────────────────────────────

def get_db():
    """Open (or reuse) the SQLite connection for this request."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    """Close the SQLite connection at the end of each request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """
    FR1 – Database initialization.
    Creates all required tables on first run:
      users, sessions, messages, feedback, analytics
    """
    db = sqlite3.connect(DATABASE_PATH)
    cursor = db.cursor()

    # Users Collection
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            google_id       TEXT UNIQUE NOT NULL,
            email           TEXT UNIQUE NOT NULL,
            name            TEXT,
            picture_url     TEXT,
            created_at      TEXT NOT NULL
        )
    """)

    # Sessions Collection
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            title       TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Messages Collection
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            user_id     TEXT NOT NULL,
            role        TEXT NOT NULL,      -- 'user' | 'assistant'
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        )
    """)

    # Feedback Collection
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id              TEXT PRIMARY KEY,
            message_id      TEXT NOT NULL,
            session_id      TEXT NOT NULL,
            user_id         TEXT NOT NULL,
            rating          INTEGER,        -- 1-5
            correctness     TEXT,           -- 'correct' | 'incorrect' | 'partial'
            length_type     TEXT,           -- 'too_short' | 'just_right' | 'too_long'
            comment         TEXT,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES messages(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logout_feedback (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            rating      INTEGER NOT NULL,
            comment     TEXT,
            created_at  TEXT NOT NULL
        )
    """)

    # Analytics Collection
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            id          TEXT PRIMARY KEY,
            user_id     TEXT,
            event_type  TEXT NOT NULL,      -- 'login' | 'message_sent' | 'feedback_given'
            metadata    TEXT,               -- JSON string
            created_at  TEXT NOT NULL
        )
    """)

    db.commit()
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(feedback)").fetchall()]
    if "comment" not in columns:
        cursor.execute("ALTER TABLE feedback ADD COLUMN comment TEXT")
        db.commit()
    db.close()
    print("[FR1] Database initialized successfully.")


# ─────────────────────────────────────────────
# HELPER UTILITIES
# ─────────────────────────────────────────────

def oauth_redirect_uri() -> str:
    """Return the callback URI Google should send users back to."""
    return GOOGLE_REDIRECT_URI or url_for("auth_callback", _external=True)


def google_credentials_path() -> str | None:
    """Find a local OAuth credentials file in the app or project root."""
    candidates = [
        os.path.join(BASE_DIR, "credentials.json"),
        os.path.join(os.path.dirname(BASE_DIR), "credentials.json"),
    ]
    return next((path for path in candidates if os.path.exists(path)), None)


def get_google_oauth_flow():
    """Initialize Google OAuth flow from credentials.json or .env values."""
    redirect_uri = oauth_redirect_uri()
    credentials_path = google_credentials_path()
    if credentials_path:
        return Flow.from_client_secrets_file(
            credentials_path,
            scopes=SCOPES,
            redirect_uri=redirect_uri,
            autogenerate_code_verifier=False,
        )

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET in your environment variables. On Vercel, add "
            "them in Project Settings > Environment Variables, then redeploy."
        )

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
        autogenerate_code_verifier=False,
    )


def safe_redirect_target(target: str | None) -> str:
    """Keep redirects inside this Flask app."""
    if not target:
        return url_for("chat")
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    if redirect_url.scheme in ("http", "https") and redirect_url.netloc == host_url.netloc:
        return redirect_url.geturl()
    return url_for("chat")


def now_iso() -> str:
    """Return current UTC datetime as ISO 8601 string."""
    return datetime.utcnow().isoformat()


def log_analytics(user_id: str, event_type: str, metadata: dict = None):
    """FR3 – Write an analytics event row."""
    db = get_db()
    db.execute(
        "INSERT INTO analytics (id, user_id, event_type, metadata, created_at) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), user_id, event_type,
         json.dumps(metadata or {}), now_iso())
    )
    db.commit()


def current_user_id() -> str | None:
    """Return the logged-in user's ID from the Flask session."""
    return session.get("user_id")


def current_user() -> dict:
    """Return the user data needed by templates."""
    return {
        "id": session.get("user_id", ""),
        "name": session.get("username", "User"),
        "email": session.get("email", ""),
        "picture": session.get("picture_url", ""),
    }


def require_login(fn):
    """Decorator – redirect to login if user is not authenticated."""
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            if request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────
# FR4: LLaMA 3 MODEL INTEGRATION (via Groq API)
# ─────────────────────────────────────────────

def json_payload() -> dict:
    """Return a JSON request body without raising a 500 for bad or empty JSON."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def user_owns_session(session_id: str) -> bool:
    """Return True when the current user owns the chat session."""
    row = get_db().execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user_id())
    ).fetchone()
    return row is not None


def build_llm_messages(history_rows) -> list:
    """Build the OpenAI-compatible message list sent to Groq."""
    return [
        {
            "role": "system",
            "content": (
                "You are a helpful, accurate, and concise AI assistant. "
                "Provide clear, structured responses. If you are unsure, say so honestly."
            )
        }
    ] + [{"role": row["role"], "content": row["content"]} for row in history_rows]


def query_llama(messages: list) -> str:
    """
    Send a conversation history to LLaMA 3 (Groq) and return the reply text.
    `messages` is a list of {"role": "user"|"assistant"|"system", "content": "..."}
    """
    if not GROQ_API_KEY:
        return "⚠️ GROQ_API_KEY is not configured. Please add it to your .env file."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLAMA_MODEL,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.7,
        "stream": False
    }

    try:
        resp = requests.post(GROQ_API_URL, headers=headers,
                             json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⚠️ Request timed out. Please try again."
    except requests.exceptions.RequestException as e:
        return f"⚠️ API error: {str(e)}"
    except (KeyError, IndexError):
        return "⚠️ Unexpected response format from the API."


# ─────────────────────────────────────────────
# FR2: FRONTEND ROUTES – Authentication
# ─────────────────────────────────────────────

@app.route("/")
def index():
    """Root – redirect to chat if logged in, else to login."""
    if current_user_id():
        return redirect(url_for("chat"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET"])
def login():
    """FR2 – Google OAuth login page."""
    if current_user_id():
        return redirect(url_for("chat"))
    return render_template("login.html")


@app.route("/auth/login")
@app.route("/auth/google")
def auth_login():
    """FR2 – Initiate Google OAuth flow."""
    try:
        flow = get_google_oauth_flow()
        session["post_auth_redirect"] = safe_redirect_target(request.args.get("next") or url_for("chat"))
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        session["oauth_state"] = state
        return redirect(authorization_url)
    except Exception as e:
        return render_template("login.html", error=f"OAuth initialization failed: {str(e)}")


@app.route("/auth/callback")
def auth_callback():
    """FR2/FR3 – Handle Google OAuth callback."""
    try:
        code = request.args.get("code")
        if not code:
            return render_template("login.html", error="Authorization failed.")
        
        flow = get_google_oauth_flow()
        flow.oauth2session.state = session.get("oauth_state")
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        
        # Get user info from Google
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
        user = db.execute(
            "SELECT id FROM users WHERE google_id = ?",
            (google_id,)
        ).fetchone()
        
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
        
        redirect_target = session.pop("post_auth_redirect", url_for("chat"))
        session.clear()
        session["user_id"] = user_id
        session["username"] = name
        session["email"] = email
        session["picture_url"] = picture_url
        log_analytics(user_id, "login")
        
        return redirect(redirect_target)
    except Exception as e:
        return render_template("login.html", error=f"Authentication failed: {str(e)}")


@app.route("/logout")
@app.route("/auth/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────────
# FR2: FRONTEND ROUTES – Chat UI
# ─────────────────────────────────────────────

@app.route("/chat")
@require_login
def chat():
    """FR2 – Main chat interface."""
    db       = get_db()
    sessions = db.execute(
        "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (current_user_id(),)
    ).fetchall()
    return render_template("chat.html",
                           user=current_user(),
                           username=session.get("username"),
                           sessions=[dict(s) for s in sessions])


@app.route("/feedback")
@require_login
def feedback_page():
    """Feedback page for rating an assistant message."""
    return render_template("feedback.html", user=current_user())


@app.route("/analytics")
@require_login
def analytics_page():
    """Analytics dashboard page."""
    return render_template("analytics.html", user=current_user())


# ─────────────────────────────────────────────
# FR3/FR4: API ROUTES – Session Management
# ─────────────────────────────────────────────

@app.route("/api/sessions", methods=["POST"])
@require_login
def create_session():
    """FR3 – Create a new chat session."""
    db         = get_db()
    session_id = str(uuid.uuid4())
    ts         = now_iso()
    title      = (json_payload().get("title") or "New Chat").strip() or "New Chat"

    db.execute(
        "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
        (session_id, current_user_id(), title, ts, ts)
    )
    db.commit()
    log_analytics(current_user_id(), "session_created", {"session_id": session_id})
    return jsonify({"session_id": session_id, "id": session_id, "title": title})


@app.route("/api/sessions", methods=["GET"])
@require_login
def list_sessions():
    """FR3 – Return all chat sessions for the logged-in user."""
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (current_user_id(),)
    ).fetchall()
    sessions = []
    for row in rows:
        item = dict(row)
        item["session_id"] = item["id"]
        sessions.append(item)
    return jsonify({"sessions": sessions})


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
@require_login
def delete_session(session_id):
    """FR3 – Delete a chat session and its messages."""
    db = get_db()
    # Verify ownership
    row = db.execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user_id())
    ).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    db.execute("DELETE FROM feedback WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    db.commit()
    return jsonify({"success": True})


# ─────────────────────────────────────────────
# FR3/FR4: API ROUTES – Messages & LLaMA 3
# ─────────────────────────────────────────────

@app.route("/api/sessions/<session_id>/messages", methods=["GET"])
@require_login
def get_messages(session_id):
    """FR3 – Fetch all messages for a session."""
    db = get_db()
    # Verify ownership
    session_row = db.execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user_id())
    ).fetchone()
    if not session_row:
        return jsonify({"error": "Not found"}), 404

    rows = db.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/sessions/<session_id>/messages", methods=["POST"])
@require_login
def send_message(session_id):
    """
    FR3/FR4 – Core message handler.
    1. Save user message
    2. Fetch conversation history
    3. Route to LLaMA 3 via Groq
    4. Save assistant response
    5. Return response to frontend
    """
    db = get_db()

    # Verify ownership
    session_row = db.execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user_id())
    ).fetchone()
    if not session_row:
        return jsonify({"error": "Not found"}), 404

    data    = json_payload()
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "Message content is required."}), 400

    ts = now_iso()

    # ── Save user message ──────────────────────
    user_msg_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (user_msg_id, session_id, current_user_id(), "user", content, ts)
    )

    # ── Build conversation history for LLaMA ──
    history_rows = db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()

    llm_messages = build_llm_messages(history_rows)

    # ── FR4: Query LLaMA 3 via Groq ────────────
    assistant_content = query_llama(llm_messages)

    # ── Save assistant response ────────────────
    asst_msg_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (asst_msg_id, session_id, current_user_id(), "assistant", assistant_content, ts)
    )

    # ── Update session timestamp & auto-title ─
    # Auto-title session from first user message
    msg_count = db.execute(
        "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?", (session_id,)
    ).fetchone()["cnt"]

    if msg_count <= 2:
        short_title = content[:40] + ("…" if len(content) > 40 else "")
        db.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (short_title, ts, session_id)
        )
    else:
        db.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (ts, session_id)
        )

    db.commit()
    log_analytics(current_user_id(), "message_sent", {"session_id": session_id})

    return jsonify({
        "session_id":            session_id,
        "user_message_id":      user_msg_id,
        "message_id":           asst_msg_id,
        "assistant_message_id": asst_msg_id,
        "assistant_content":    assistant_content,
        "response":             assistant_content,
        "timestamp":            ts,
    })


def session_summaries():
    """Return chat sessions in the shape used by the frontend."""
    rows = get_db().execute(
        """
        SELECT cs.id AS session_id,
               cs.title,
               cs.created_at,
               cs.updated_at,
               COUNT(m.id) AS message_count
        FROM chat_sessions cs
        LEFT JOIN messages m ON m.session_id = cs.id
        WHERE cs.user_id = ?
        GROUP BY cs.id
        ORDER BY cs.updated_at DESC
        """,
        (current_user_id(),)
    ).fetchall()
    return [dict(row) for row in rows]


@app.route("/chat/sessions", methods=["GET"])
@require_login
def chat_sessions_frontend():
    """Frontend-compatible session list."""
    return jsonify({"sessions": session_summaries()})


@app.route("/chat/history/<session_id>", methods=["GET"])
@require_login
def chat_history_frontend(session_id):
    """Frontend-compatible chat history."""
    db = get_db()
    session_row = db.execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user_id())
    ).fetchone()
    if not session_row:
        return jsonify({"error": "Not found"}), 404

    rows = db.execute(
        "SELECT id, role, content, created_at AS timestamp FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    return jsonify({"messages": [dict(row) for row in rows]})


@app.route("/chat/session/<session_id>", methods=["DELETE"])
@require_login
def delete_session_frontend(session_id):
    """Frontend-compatible session delete."""
    return delete_session(session_id)


@app.route("/chat/send", methods=["POST"])
@require_login
def send_message_frontend():
    """Frontend-compatible message endpoint that creates a session on demand."""
    db = get_db()
    data = json_payload()
    content = data.get("content", "").strip()
    session_id = data.get("session_id")

    if not content:
        return jsonify({"error": "Message content is required."}), 400

    ts = now_iso()
    if not session_id:
        session_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
            (session_id, current_user_id(), "New Chat", ts, ts)
        )
        db.commit()
    else:
        owner = db.execute(
            "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, current_user_id())
        ).fetchone()
        if not owner:
            return jsonify({"error": "Not found"}), 404

    user_msg_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (user_msg_id, session_id, current_user_id(), "user", content, ts)
    )

    history_rows = db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    llm_messages = build_llm_messages(history_rows)

    assistant_content = query_llama(llm_messages)
    assistant_msg_id = str(uuid.uuid4())
    reply_ts = now_iso()
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (assistant_msg_id, session_id, current_user_id(), "assistant", assistant_content, reply_ts)
    )

    msg_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE session_id = ?",
        (session_id,)
    ).fetchone()["cnt"]
    if msg_count <= 2:
        title = content[:40] + ("..." if len(content) > 40 else "")
        db.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, reply_ts, session_id)
        )
    else:
        db.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (reply_ts, session_id)
        )

    db.commit()
    log_analytics(current_user_id(), "message_sent", {"session_id": session_id})

    return jsonify({
        "session_id": session_id,
        "user_message_id": user_msg_id,
        "message_id": assistant_msg_id,
        "response": assistant_content,
        "timestamp": reply_ts,
    })


# ─────────────────────────────────────────────
# FR2/FR3: API ROUTES – Feedback Panel
# ─────────────────────────────────────────────

@app.route("/api/feedback", methods=["POST"])
@require_login
def submit_feedback():
    """
    FR2/FR3 – Accept user feedback on an assistant message.
    Stores: rating (1-5), correctness, length_type
    """
    db   = get_db()
    data = json_payload()

    message_id  = data.get("message_id")
    session_id  = data.get("session_id")
    rating      = data.get("rating")          # 1-5
    correctness = data.get("correctness")     # 'correct'|'incorrect'|'partial'
    length_type = data.get("length_type") or data.get("length_rating")
    comment     = data.get("comment")

    if not message_id or not session_id:
        return jsonify({"error": "message_id and session_id are required."}), 400

    message = db.execute(
        """
        SELECT id FROM messages
        WHERE id = ? AND session_id = ? AND user_id = ? AND role = 'assistant'
        """,
        (message_id, session_id, current_user_id())
    ).fetchone()
    if not message:
        return jsonify({"error": "Assistant message not found."}), 404

    # Check if feedback already submitted for this message
    existing = db.execute(
        "SELECT id FROM feedback WHERE message_id = ? AND user_id = ?",
        (message_id, current_user_id())
    ).fetchone()

    if existing:
        # Update existing feedback
        db.execute(
            "UPDATE feedback SET rating=?, correctness=?, length_type=?, comment=? WHERE message_id=? AND user_id=?",
            (rating, correctness, length_type, comment, message_id, current_user_id())
        )
    else:
        # Insert new feedback
        db.execute(
            """INSERT INTO feedback
               (id, message_id, session_id, user_id, rating, correctness, length_type, comment, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), message_id, session_id,
             current_user_id(), rating, correctness, length_type, comment, now_iso())
        )

    db.commit()
    log_analytics(current_user_id(), "feedback_given",
                  {"message_id": message_id, "rating": rating})
    return jsonify({"success": True})


@app.route("/feedback/submit", methods=["POST"])
@require_login
def submit_feedback_frontend():
    """Frontend-compatible alias for message feedback."""
    return submit_feedback()


@app.route("/feedback/logout", methods=["POST"])
@require_login
def submit_logout_feedback():
    """Store optional feedback collected before logout."""
    data = json_payload()
    rating = data.get("rating")
    if not rating:
        return jsonify({"error": "rating is required."}), 400

    db = get_db()
    db.execute(
        "INSERT INTO logout_feedback (id, user_id, rating, comment, created_at) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), current_user_id(), rating, data.get("comment"), now_iso())
    )
    db.commit()
    log_analytics(current_user_id(), "logout_feedback", {"rating": rating})
    return jsonify({"success": True})


def svg_chart(title, labels, values, chart_type="bar"):
    """Build a lightweight data-uri SVG chart for the analytics page."""
    total = sum(values) or 1
    colors = ["#60a5fa", "#22c55e", "#f59e0b", "#ef4444", "#a78bfa", "#14b8a6"]

    if chart_type == "pie":
        rows = "".join(
            f"<text x='28' y='{76 + i * 26}' fill='#cbd5e1' font-size='14'>"
            f"<tspan fill='{colors[i % len(colors)]}'>■</tspan> {label}: {value}</text>"
            for i, (label, value) in enumerate(zip(labels, values))
        )
        body = rows or "<text x='28' y='86' fill='#94a3b8' font-size='14'>No data yet</text>"
    else:
        bars = []
        for i, (label, value) in enumerate(zip(labels, values)):
            width = int((value / max(values or [1])) * 300) if values else 0
            y = 78 + i * 38
            bars.append(f"<text x='28' y='{y + 15}' fill='#cbd5e1' font-size='13'>{label}</text>")
            bars.append(f"<rect x='140' y='{y}' width='{width}' height='20' rx='4' fill='{colors[i % len(colors)]}'/>")
            bars.append(f"<text x='{150 + width}' y='{y + 15}' fill='#f8fafc' font-size='13'>{value}</text>")
        body = "".join(bars) or "<text x='28' y='86' fill='#94a3b8' font-size='14'>No data yet</text>"

    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'>"
        "<rect width='640' height='360' rx='8' fill='#172033'/>"
        f"<text x='28' y='42' fill='#f8fafc' font-size='20' font-family='Arial'>{title}</text>"
        f"{body}"
        "</svg>"
    )
    return f"data:image/svg+xml;charset=utf-8,{quote(svg)}"


def user_message_topics():
    """Classify user messages with simple keyword buckets for dashboard display."""
    rows = get_db().execute(
        """
        SELECT content
        FROM messages
        WHERE user_id = ? AND role = 'user'
        """,
        (current_user_id(),)
    ).fetchall()
    buckets = Counter()
    keywords = {
        "Coding": ("python", "code", "function", "bug", "javascript", "html", "css", "api"),
        "Study": ("study", "learn", "exam", "assignment", "explain", "notes"),
        "Writing": ("write", "essay", "email", "summary", "letter"),
        "General": (),
    }
    for row in rows:
        text = row["content"].lower()
        topic = "General"
        for name, words in keywords.items():
            if words and any(word in text for word in words):
                topic = name
                break
        buckets[topic] += 1
    return buckets


@app.route("/analytics/stats", methods=["GET"])
@require_login
def analytics_stats():
    db = get_db()
    total_messages = db.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE user_id = ?",
        (current_user_id(),)
    ).fetchone()["cnt"]
    user_messages = db.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE user_id = ? AND role = 'user'",
        (current_user_id(),)
    ).fetchone()["cnt"]
    assistant_messages = db.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE user_id = ? AND role = 'assistant'",
        (current_user_id(),)
    ).fetchone()["cnt"]
    total_sessions = db.execute(
        "SELECT COUNT(*) AS cnt FROM chat_sessions WHERE user_id = ?",
        (current_user_id(),)
    ).fetchone()["cnt"]
    messages_last_7_days = db.execute(
        "SELECT COUNT(*) AS cnt FROM messages WHERE user_id = ? AND created_at >= datetime('now', '-7 days')",
        (current_user_id(),)
    ).fetchone()["cnt"]
    feedback_row = db.execute(
        "SELECT COUNT(*) AS cnt, AVG(rating) AS avg_rating FROM feedback WHERE user_id = ?",
        (current_user_id(),)
    ).fetchone()
    topics = user_message_topics()

    return jsonify({
        "total_messages": total_messages,
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        "total_sessions": total_sessions,
        "messages_last_7_days": messages_last_7_days,
        "total_feedback": feedback_row["cnt"],
        "avg_rating": round(feedback_row["avg_rating"], 1) if feedback_row["avg_rating"] else None,
        "avg_messages_per_session": round(total_messages / total_sessions, 1) if total_sessions else 0,
        "top_topic": topics.most_common(1)[0][0] if topics else None,
    })


@app.route("/analytics/graphs", methods=["GET"])
@require_login
def analytics_graphs():
    db = get_db()
    daily_rows = db.execute(
        """
        SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS cnt
        FROM messages
        WHERE user_id = ?
        GROUP BY day
        ORDER BY day DESC
        LIMIT 7
        """,
        (current_user_id(),)
    ).fetchall()
    daily = list(reversed([(row["day"], row["cnt"]) for row in daily_rows]))

    correctness_rows = db.execute(
        "SELECT correctness, COUNT(*) AS cnt FROM feedback WHERE user_id = ? GROUP BY correctness",
        (current_user_id(),)
    ).fetchall()
    ratings_rows = db.execute(
        "SELECT rating, COUNT(*) AS cnt FROM feedback WHERE user_id = ? GROUP BY rating ORDER BY rating",
        (current_user_id(),)
    ).fetchall()
    topics = user_message_topics()

    topic_labels = list(topics.keys())
    topic_values = list(topics.values())
    return jsonify({
        "daily_activity": svg_chart(
            "Daily Activity",
            [day for day, _ in daily],
            [count for _, count in daily],
        ),
        "correctness_pie": svg_chart(
            "Response Correctness",
            [row["correctness"] or "unspecified" for row in correctness_rows],
            [row["cnt"] for row in correctness_rows],
            "pie",
        ),
        "rating_dist": svg_chart(
            "Rating Distribution",
            [f"{row['rating']} star" for row in ratings_rows],
            [row["cnt"] for row in ratings_rows],
        ),
        "topic_plot": {
            "data": [{
                "type": "bar",
                "x": topic_labels,
                "y": topic_values,
                "marker": {"color": "#60a5fa"},
            }],
            "layout": {
                "paper_bgcolor": "#172033",
                "plot_bgcolor": "#172033",
                "font": {"color": "#cbd5e1"},
                "margin": {"l": 40, "r": 20, "t": 20, "b": 40},
            },
        },
    })


@app.route("/feedback/list", methods=["GET"])
@require_login
def feedback_list():
    db = get_db()
    feedback_rows = db.execute(
        """
        SELECT rating, correctness, length_type AS length_rating, comment, created_at AS submitted_at
        FROM feedback
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (current_user_id(),)
    ).fetchall()
    logout_rows = db.execute(
        """
        SELECT rating, comment, created_at AS submitted_at
        FROM logout_feedback
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (current_user_id(),)
    ).fetchall()
    return jsonify({
        "feedback": [dict(row) for row in feedback_rows],
        "logout_feedback": [dict(row) for row in logout_rows],
    })


@app.route("/analytics/health", methods=["GET"])
def analytics_health():
    return health_check()


# ─────────────────────────────────────────────
# FR5: SERVICE CONNECTIVITY – Health Check
# ─────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health_check():
    """
    FR5 – Verify all services are reachable:
    backend, database, and Groq API key presence.
    """
    db_ok    = False
    groq_ok  = bool(GROQ_API_KEY)
    oauth_ok = bool(google_credentials_path() or (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET))

    try:
        db = get_db()
        db.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    return jsonify({
        "status":    "ok" if (db_ok and groq_ok and oauth_ok) else "degraded",
        "database":  "connected" if db_ok else "error",
        "groq_api":  "configured" if groq_ok else "missing",
        "google_oauth": "configured" if oauth_ok else "missing",
        "model":     LLAMA_MODEL,
        "timestamp": now_iso()
    })


# ─────────────────────────────────────────────
# FR1: APPLICATION BOOTSTRAP
# ─────────────────────────────────────────────

init_db()


if __name__ == "__main__":
    print("[FR1] System initialization complete.")
    print(f"[FR4] Using model: {LLAMA_MODEL} via Groq API")
    print(f"[FR5] Starting Flask server on http://127.0.0.1:{APP_PORT}")
    app.run(debug=True, port=APP_PORT)
