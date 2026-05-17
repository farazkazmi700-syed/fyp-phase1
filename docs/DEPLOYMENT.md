# Flask Vercel Deployment

## Folder Structure

```text
.
├── app.py                  # Vercel/WSGI entrypoint: imports backend.app:app
├── api/
│   └── index.py            # Vercel Python Function entrypoint
├── backend/
│   ├── __init__.py
│   ├── app.py              # Main Flask application
│   ├── static/             # CSS and browser JavaScript
│   └── templates/          # Jinja templates
├── requirements.txt        # Python dependencies
├── vercel.json             # Vercel project config
├── runtime.txt             # Python runtime hint
├── .python-version         # Python version hint
├── .gitignore
└── .vercelignore
```

## Local Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Vercel Entry Point

Use the Vercel Python Function file:

```text
api/index.py
```

It exports the Flask app:

```python
from backend.app import app
```

`vercel.json` rewrites all incoming paths to this function, so Flask handles `/`, `/login`, `/chat`, `/api/health`, and the rest of the app routes.

## Vercel Environment Variables

Set these in the Vercel project dashboard:

```text
FLASK_SECRET_KEY
GROQ_API_KEY
GROQ_MODEL
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
```

For production Google OAuth, set:

```text
GOOGLE_REDIRECT_URI=https://your-vercel-domain.vercel.app/auth/callback
```

## Database Note

Local development uses `backend/chatbot.db` by default.

On Vercel, SQLite uses `/tmp/chatbot.db` because the deployed filesystem is serverless and not persistent. For real production data, replace SQLite with a hosted database such as Vercel Postgres, Neon, Supabase, or another managed database.
