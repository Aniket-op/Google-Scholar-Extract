"""
api/index.py — Vercel serverless entry point for the Google Scholar Extractor.

Vercel's Python runtime looks for a WSGI-compatible `app` object in this file.
This module simply adds the backend package to sys.path and re-exports the
Flask `app` from backend/app.py.

NOTE — Serverless limitations:
  - The in-memory `jobs` dict resets on every cold start.  Each invocation of
    POST /api/extract and the subsequent GET /api/status/* MUST hit the same
    warm lambda instance.  Because Vercel does NOT guarantee sticky routing,
    long-running extractions may fail if the instance is recycled between polls.
  - Background threads spun up by Flask are supported within a single lambda
    execution, but the lambda will be killed after `maxDuration` seconds
    (configured to 60 s in vercel.json).  Profiles with many publications may
    exceed this limit.
  - For production use, replace the in-memory job store with an external
    store (Redis, Upstash, Supabase, etc.) and use a queue/worker pattern.
"""

import os
import sys

# ── Add backend directory to the module search path ──────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_HERE, "..", "backend")
sys.path.insert(0, os.path.abspath(_BACKEND))

# ── Import the Flask application ─────────────────────────────────────────────
# Vercel's Python runtime expects the WSGI app to be named `app` or `handler`.
from app import app  # noqa: E402  (import after sys.path manipulation)

# Re-export so Vercel picks it up
__all__ = ["app"]
