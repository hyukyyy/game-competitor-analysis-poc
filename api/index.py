"""Vercel Python serverless entrypoint for the FastAPI app.

Vercel's Python runtime looks for a module-level `app` ASGI callable. This
module re-exports the FastAPI instance defined in ``gca.api.server``. Only
lean (read-only) dependencies listed in ``api/requirements.txt`` are
available in the function bundle — do NOT import ML modules here.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Vercel sets cwd to the repo root; ensure the ``src`` layout is importable.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from gca.api.server import app  # noqa: E402

# Vercel Python runtime expects `app` (ASGI) or `handler`. Export both.
handler = app

__all__ = ["app", "handler"]
