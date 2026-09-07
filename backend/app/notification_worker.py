"""Run with python -m app.notification_worker; --once drains the currently due queue."""

import argparse
import asyncio
import logging
import time

from app.config import settings
from app.database import async_session, engine
from app.services.email_delivery_service import (
    deliver_next,
    recover_interrupted,
    validate_email_config,
)

logger = logging.getLogger(__name__)


async def run(once: bool = False) -> int:
    validate_email_config()
    if not settings.email_delivery_enabled:
        raise RuntimeError("Set EMAIL_DELIVERY_ENABLED=true before starting the notice worker")
    if settings.demo_isolated_sessions:
        raise RuntimeError("The notice worker does not operate on isolated demo sessions")
    last_recovery = time.monotonic() - 60
    failed = False
    try:
        while True:
            try:
                if time.monotonic() - last_recovery >= 60:
                    await recover_interrupted(async_session)
                    last_recovery = time.monotonic()
                if not await deliver_next(async_session):
                    if once:
                        return int(failed)
                    await asyncio.sleep(5)
            except Exception:
                failed = True
                logger.exception("Notice delivery iteration failed")
                if once:
                    return 1
                await asyncio.sleep(5)
    finally:
        await engine.dispose()
    return int(failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(run(once=parser.parse_args().once)))
