import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")

load_dotenv(os.path.join(PROJECT_DIR, ".env"))
load_dotenv(os.path.join(BASE_DIR, ".env"))
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
    GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
    LLAMA_MODEL = os.getenv("GROQ_MODEL") or os.getenv("LLAMA_MODEL") or "llama-3.1-8b-instant"

    DEFAULT_DATABASE_PATH = os.path.join(BASE_DIR, "chatbot.db")
    DATABASE_PATH = os.getenv("DATABASE_PATH") or DEFAULT_DATABASE_PATH
    if not os.path.isabs(DATABASE_PATH):
        DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_PATH)

    APP_PORT = int(os.getenv("APP_PORT", "5000"))

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "")

    SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email",
    ]
