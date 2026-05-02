"""Centralized logging setup.

Goal: emit one consistent line format across uvicorn / app / sqlalchemy and surface the
``X-Request-ID`` header value automatically when a handler logged something during a
request. Configuration is idempotent so running tests / re-importing ``app.main`` is safe.
"""

from __future__ import annotations

import contextvars
import logging
import os

# Per-request id propagated via a contextvar so deeply-nested code (services, ORM events)
# can include it in log records without threading the request through every signature.
_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "muefs_request_id", default=None
)


def set_request_id(request_id: str | None) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    return _request_id_var.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - logging Filter API
        record.request_id = _request_id_var.get() or "-"
        return True


_DEFAULT_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s [req=%(request_id)s] %(message)s"
)
_DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S"

_configured = False


def configure_logging(level: str | None = None) -> None:
    """Idempotent root logger setup.

    Resolution order for level: explicit arg → ``LOG_LEVEL`` env → ``INFO``. Calling
    twice has no effect; reconfiguration is intentional but rare.
    """
    global _configured
    if _configured:
        return
    resolved = (level or os.getenv("LOG_LEVEL") or "INFO").upper()

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATEFMT))
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    # Replace existing handlers so we control the format end-to-end (uvicorn installs its
    # own; we keep the level high enough that they remain useful but the format is unified).
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(resolved)

    # Quiet down libraries we don't want flooding the logs at INFO.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
