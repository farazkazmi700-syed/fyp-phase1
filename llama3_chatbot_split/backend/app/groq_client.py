import requests
from .config import Config


def build_llm_messages(history_rows) -> list:
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
    if not Config.GROQ_API_KEY:
        return "GROQ_API_KEY is not configured. Please add it to your .env file."

    headers = {
        "Authorization": f"Bearer {Config.GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": Config.LLAMA_MODEL,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.7,
        "stream": False
    }

    try:
        resp = requests.post(Config.GROQ_API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "Request timed out. Please try again."
    except requests.exceptions.RequestException as e:
        return f"API error: {str(e)}"
    except (KeyError, IndexError):
        return "Unexpected response format from the API."
