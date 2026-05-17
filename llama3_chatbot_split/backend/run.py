from app import create_app
from app.config import Config

app = create_app()

if __name__ == "__main__":
    print("System initialization complete.")
    print(f"Using model: {Config.LLAMA_MODEL} via Groq API")
    print(f"Starting Flask server on http://127.0.0.1:{Config.APP_PORT}")
    app.run(debug=True, port=Config.APP_PORT)
