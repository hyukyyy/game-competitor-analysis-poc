from __future__ import annotations

import logging

from .config import settings

_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
        )
        _configured = True
    return logging.getLogger(name)
