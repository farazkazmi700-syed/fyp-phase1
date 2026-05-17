"""Vercel and WSGI entrypoint.

Vercel's Flask runtime looks for a top-level Flask object named `app` in
recognized entrypoints such as this root `app.py`.
"""

from backend.app import app

