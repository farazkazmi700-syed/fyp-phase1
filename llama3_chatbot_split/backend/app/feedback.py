import uuid
from flask import Blueprint, render_template, jsonify
from .database import get_db
from .utils import require_login, current_user, current_user_id, json_payload, now_iso, log_analytics

feedback_bp = Blueprint("feedback", __name__)


@feedback_bp.route("/feedback")
@require_login
def feedback_page():
    return render_template("feedback.html", user=current_user())


@feedback_bp.route("/api/feedback", methods=["POST"])
@require_login
def submit_feedback():
    db = get_db()
    data = json_payload()

    message_id = data.get("message_id")
    session_id = data.get("session_id")
    rating = data.get("rating")
    correctness = data.get("correctness")
    length_type = data.get("length_type") or data.get("length_rating")
    comment = data.get("comment")

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

    existing = db.execute(
        "SELECT id FROM feedback WHERE message_id = ? AND user_id = ?",
        (message_id, current_user_id())
    ).fetchone()

    if existing:
        db.execute(
            "UPDATE feedback SET rating=?, correctness=?, length_type=?, comment=? WHERE message_id=? AND user_id=?",
            (rating, correctness, length_type, comment, message_id, current_user_id())
        )
    else:
        db.execute(
            """INSERT INTO feedback
               (id, message_id, session_id, user_id, rating, correctness, length_type, comment, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), message_id, session_id, current_user_id(), rating, correctness, length_type, comment, now_iso())
        )

    db.commit()
    log_analytics(current_user_id(), "feedback_given", {"message_id": message_id, "rating": rating})
    return jsonify({"success": True})


@feedback_bp.route("/feedback/submit", methods=["POST"])
@require_login
def submit_feedback_frontend():
    return submit_feedback()


@feedback_bp.route("/feedback/logout", methods=["POST"])
@require_login
def submit_logout_feedback():
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


@feedback_bp.route("/feedback/list", methods=["GET"])
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
