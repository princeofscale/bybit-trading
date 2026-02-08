import asyncio
import os
import signal
from pathlib import Path

import structlog

from config.settings import get_settings
from config.strategy_profiles import RiskProfile, get_profile
from core.orchestrator import TradingOrchestrator
from monitoring.logger import setup_logging

logger = structlog.get_logger("main")


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)

    profile_name = os.environ.get("RISK_PROFILE", "moderate")
    profile = get_profile(RiskProfile(profile_name))

    journal_path = Path("journal.db")

    orchestrator = TradingOrchestrator(settings, profile, journal_path)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, orchestrator.request_shutdown)

    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
