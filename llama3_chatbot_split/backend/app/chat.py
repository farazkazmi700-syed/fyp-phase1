import uuid
from flask import Blueprint, render_template, jsonify
from .database import get_db
from .utils import require_login, current_user_id, current_user, json_payload, now_iso, log_analytics
from .groq_client import build_llm_messages, query_llama

chat_bp = Blueprint("chat", __name__)


def user_owns_session(session_id: str) -> bool:
    row = get_db().execute(
        "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, current_user_id())
    ).fetchone()
    return row is not None


@chat_bp.route("/chat")
@require_login
def chat_page():
    db = get_db()
    sessions = db.execute(
        "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (current_user_id(),)
    ).fetchall()
    return render_template(
        "chat.html",
        user=current_user(),
        username=current_user().get("name"),
        sessions=[dict(s) for s in sessions]
    )


@chat_bp.route("/api/sessions", methods=["POST"])
@require_login
def create_session():
    db = get_db()
    session_id = str(uuid.uuid4())
    ts = now_iso()
    title = (json_payload().get("title") or "New Chat").strip() or "New Chat"

    db.execute(
        "INSERT INTO chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
        (session_id, current_user_id(), title, ts, ts)
    )
    db.commit()
    log_analytics(current_user_id(), "session_created", {"session_id": session_id})
    return jsonify({"session_id": session_id, "id": session_id, "title": title})


@chat_bp.route("/api/sessions", methods=["GET"])
@require_login
def list_sessions():
    db = get_db()
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


@chat_bp.route("/api/sessions/<session_id>", methods=["DELETE"])
@require_login
def delete_session(session_id):
    db = get_db()
    if not user_owns_session(session_id):
        return jsonify({"error": "Not found"}), 404

    db.execute("DELETE FROM feedback WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    db.commit()
    return jsonify({"success": True})


@chat_bp.route("/api/sessions/<session_id>/messages", methods=["GET"])
@require_login
def get_messages(session_id):
    db = get_db()
    if not user_owns_session(session_id):
        return jsonify({"error": "Not found"}), 404

    rows = db.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@chat_bp.route("/api/sessions/<session_id>/messages", methods=["POST"])
@require_login
def send_message(session_id):
    db = get_db()
    if not user_owns_session(session_id):
        return jsonify({"error": "Not found"}), 404

    data = json_payload()
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "Message content is required."}), 400

    ts = now_iso()
    user_msg_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (user_msg_id, session_id, current_user_id(), "user", content, ts)
    )

    history_rows = db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    assistant_content = query_llama(build_llm_messages(history_rows))

    asst_msg_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (asst_msg_id, session_id, current_user_id(), "assistant", assistant_content, ts)
    )

    msg_count = db.execute(
        "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?", (session_id,)
    ).fetchone()["cnt"]

    if msg_count <= 2:
        short_title = content[:40] + ("..." if len(content) > 40 else "")
        db.execute("UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?", (short_title, ts, session_id))
    else:
        db.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (ts, session_id))

    db.commit()
    log_analytics(current_user_id(), "message_sent", {"session_id": session_id})

    return jsonify({
        "session_id": session_id,
        "user_message_id": user_msg_id,
        "message_id": asst_msg_id,
        "assistant_message_id": asst_msg_id,
        "assistant_content": assistant_content,
        "response": assistant_content,
        "timestamp": ts,
    })


def session_summaries():
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


@chat_bp.route("/chat/sessions", methods=["GET"])
@require_login
def chat_sessions_frontend():
    return jsonify({"sessions": session_summaries()})


@chat_bp.route("/chat/history/<session_id>", methods=["GET"])
@require_login
def chat_history_frontend(session_id):
    db = get_db()
    if not user_owns_session(session_id):
        return jsonify({"error": "Not found"}), 404

    rows = db.execute(
        "SELECT id, role, content, created_at AS timestamp FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    return jsonify({"messages": [dict(row) for row in rows]})


@chat_bp.route("/chat/session/<session_id>", methods=["DELETE"])
@require_login
def delete_session_frontend(session_id):
    return delete_session(session_id)


@chat_bp.route("/chat/send", methods=["POST"])
@require_login
def send_message_frontend():
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
    elif not user_owns_session(session_id):
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
    assistant_content = query_llama(build_llm_messages(history_rows))

    assistant_msg_id = str(uuid.uuid4())
    reply_ts = now_iso()
    db.execute(
        "INSERT INTO messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
        (assistant_msg_id, session_id, current_user_id(), "assistant", assistant_content, reply_ts)
    )

    msg_count = db.execute("SELECT COUNT(*) AS cnt FROM messages WHERE session_id = ?", (session_id,)).fetchone()["cnt"]
    if msg_count <= 2:
        title = content[:40] + ("..." if len(content) > 40 else "")
        db.execute("UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?", (title, reply_ts, session_id))
    else:
        db.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (reply_ts, session_id))

    db.commit()
    log_analytics(current_user_id(), "message_sent", {"session_id": session_id})

    return jsonify({
        "session_id": session_id,
        "user_message_id": user_msg_id,
        "message_id": assistant_msg_id,
        "response": assistant_content,
        "timestamp": reply_ts,
    })
