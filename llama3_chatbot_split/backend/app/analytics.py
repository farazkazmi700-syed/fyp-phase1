from collections import Counter
from urllib.parse import quote
from flask import Blueprint, render_template, jsonify
from .database import get_db
from .utils import require_login, current_user, current_user_id, now_iso
from .config import Config
from .auth import google_credentials_path

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
@require_login
def analytics_page():
    return render_template("analytics.html", user=current_user())


def svg_chart(title, labels, values, chart_type="bar"):
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
    rows = get_db().execute(
        "SELECT content FROM messages WHERE user_id = ? AND role = 'user'",
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


@analytics_bp.route("/analytics/stats", methods=["GET"])
@require_login
def analytics_stats():
    db = get_db()
    total_messages = db.execute("SELECT COUNT(*) AS cnt FROM messages WHERE user_id = ?", (current_user_id(),)).fetchone()["cnt"]
    user_messages = db.execute("SELECT COUNT(*) AS cnt FROM messages WHERE user_id = ? AND role = 'user'", (current_user_id(),)).fetchone()["cnt"]
    assistant_messages = db.execute("SELECT COUNT(*) AS cnt FROM messages WHERE user_id = ? AND role = 'assistant'", (current_user_id(),)).fetchone()["cnt"]
    total_sessions = db.execute("SELECT COUNT(*) AS cnt FROM chat_sessions WHERE user_id = ?", (current_user_id(),)).fetchone()["cnt"]
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


@analytics_bp.route("/analytics/graphs", methods=["GET"])
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

    return jsonify({
        "daily_activity": svg_chart("Daily Activity", [day for day, _ in daily], [count for _, count in daily]),
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
            "data": [{"type": "bar", "x": list(topics.keys()), "y": list(topics.values()), "marker": {"color": "#60a5fa"}}],
            "layout": {
                "paper_bgcolor": "#172033",
                "plot_bgcolor": "#172033",
                "font": {"color": "#cbd5e1"},
                "margin": {"l": 40, "r": 20, "t": 20, "b": 40},
            },
        },
    })


@analytics_bp.route("/api/health", methods=["GET"])
def health_check():
    db_ok = False
    groq_ok = bool(Config.GROQ_API_KEY)
    oauth_ok = bool(google_credentials_path() or (Config.GOOGLE_CLIENT_ID and Config.GOOGLE_CLIENT_SECRET))

    try:
        db = get_db()
        db.execute("SELECT 1")
        db_ok = True
    except Exception:
        pass

    return jsonify({
        "status": "ok" if (db_ok and groq_ok and oauth_ok) else "degraded",
        "database": "connected" if db_ok else "error",
        "groq_api": "configured" if groq_ok else "missing",
        "google_oauth": "configured" if oauth_ok else "missing",
        "model": Config.LLAMA_MODEL,
        "timestamp": now_iso()
    })


@analytics_bp.route("/analytics/health", methods=["GET"])
def analytics_health():
    return health_check()
