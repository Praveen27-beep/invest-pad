"""Vercel Serverless Function entrypoint for trackr-backend.

Routes all incoming HTTP requests to FastAPI application instance.
"""

import os
import sys

# Ensure the backend root directory is in sys.path for Vercel imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402

__all__ = ["app"]

