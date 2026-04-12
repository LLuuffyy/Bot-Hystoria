import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import Stealth

from config import Config, load_config
from logger_setup import setup_logging
from auth import login, is_logged_in, wait_for_cloudflare
from voter import attempt_vote, VoteResult
from cooldown import extract_cooldown_from_page

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 5
FAILURE_COOLDOWN_SECONDS = 1800  # 30 minutes

# Path to store persistent browser profile (survives restarts)
BROWSER_DATA_DIR = Path("state/browser_profile")


async def ensure_logged_in(page: Page, context: BrowserContext, config: Config) -> bool:
    """Make sure we're logged in, attempt login if not."""
    try:
        await page.goto(config.base_url, wait_until="networkidle", timeout=60000)
        await wait_for_cloudflare(page)

        if await is_logged_in(page):
            logger.debug("Session is valid")
            return True
    except Exception as e:
        logger.warning("Error checking login status: %s", e)

    logger.info("Session expired or not logged in. Attempting login...")
    return await login(page, context, config)


async def main() -> None:
    setup_logging()
    config = load_config()

    logger.info("=== Bot-Hystoria Auto-Voter ===")
    logger.info("User: %s", config.username)
    logger.info("Vote interval: %d minutes", config.vote_interval)
    logger.info("Headless: %s", config.headless)
    logger.info("URL: %s", config.base_url)

    # Ensure runtime directories exist
    Path("state").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    consecutive_failures = 0

    async with async_playwright() as pw:
        # Use a persistent browser context with the real Chrome browser
        # This looks like a real user's Chrome, not an automated browser
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            channel="chrome",  # Use the real Chrome installed on the PC
            headless=config.headless,
            slow_mo=100,
            viewport={"width": 1280, "height": 720},
            ignore_default_args=["--enable-automation"],  # Remove the automation banner
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        # Apply stealth patches to hide automation indicators
        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = context.pages[0] if context.pages else await context.new_page()

        logger.info("Chrome launched. Starting vote loop...")

        while True:
            try:
                # Ensure we're logged in
                logged_in = await ensure_logged_in(page, context, config)
                if not logged_in:
                    logger.error("Failed to log in. Retrying in 2 minutes...")
                    await asyncio.sleep(120)
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        await _handle_max_failures(consecutive_failures)
                    continue

                # Attempt to vote
                result = await attempt_vote(page, context, config)

                if result == VoteResult.SUCCESS:
                    consecutive_failures = 0
                    wait_minutes = config.vote_interval
                    logger.info(
                        "Vote successful! Next vote in %d minutes.", wait_minutes
                    )
                    await asyncio.sleep(wait_minutes * 60)

                elif result == VoteResult.COOLDOWN:
                    consecutive_failures = 0
                    remaining = await extract_cooldown_from_page(page)
                    if remaining:
                        wait_seconds = remaining + 60  # 1 min buffer
                        logger.info(
                            "Cooldown active. Waiting %d minutes %d seconds.",
                            wait_seconds // 60,
                            wait_seconds % 60,
                        )
                    else:
                        wait_seconds = config.vote_interval * 60
                        logger.info(
                            "Cooldown active but timer not parsed. Waiting %d minutes.",
                            config.vote_interval,
                        )
                    await asyncio.sleep(wait_seconds)

                elif result == VoteResult.NOT_LOGGED_IN:
                    logger.warning("Not logged in during vote. Will re-login next loop.")
                    consecutive_failures += 1
                    await asyncio.sleep(30)

                elif result == VoteResult.ERROR:
                    consecutive_failures += 1
                    logger.warning(
                        "Vote error (%d/%d failures). Retrying in 60s...",
                        consecutive_failures,
                        MAX_CONSECUTIVE_FAILURES,
                    )
                    await asyncio.sleep(60)

                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    await _handle_max_failures(consecutive_failures)
                    consecutive_failures = 0

            except KeyboardInterrupt:
                logger.info("Bot stopped by user.")
                break

            except Exception as e:
                consecutive_failures += 1
                logger.exception("Unexpected error: %s", e)
                logger.info("Retrying in 2 minutes...")
                await asyncio.sleep(120)

        # Cleanup
        await context.close()
        logger.info("Bot shutdown complete.")


async def _handle_max_failures(count: int) -> None:
    """Handle too many consecutive failures."""
    logger.critical(
        "%d consecutive failures. Pausing for %d minutes before retrying...",
        count,
        FAILURE_COOLDOWN_SECONDS // 60,
    )
    await asyncio.sleep(FAILURE_COOLDOWN_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
