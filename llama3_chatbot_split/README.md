# Multi-Turn AI Chatbot Flask Project

This project is the separated version of the original single-file Flask app.

## Folder Structure

```text
backend/
  app/
    __init__.py
    config.py
    database.py
    utils.py
    auth.py
    chat.py
    feedback.py
    analytics.py
    groq_client.py
  run.py
  requirements.txt
frontend/
  templates/
    login.html
    chat.html
    feedback.html
    analytics.html
  static/
    css/style.css
    js/chat.js
.env.example
```

## Run Step by Step

### 1. Open project folder

```bash
cd backend
```

### 2. Create virtual environment

```bash
python -m venv venv
```

### 3. Activate virtual environment

Windows:

```bash
venv\Scripts\activate
```

Linux/Mac:

```bash
source venv/bin/activate
```

### 4. Install packages

```bash
pip install -r requirements.txt
```

### 5. Create `.env`

Copy `.env.example` to `.env` in the project root or backend folder and add your real keys.

### 6. Run app

```bash
python run.py
```

Open:

```text
http://127.0.0.1:5000
```

## Important

The file must be named `__init__.py`, not `--init.py`.
