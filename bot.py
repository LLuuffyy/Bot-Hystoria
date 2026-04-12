import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Page

from config import Config, load_config
from logger_setup import setup_logging
from auth import login, is_logged_in, wait_for_cloudflare
from voter import attempt_vote, VoteResult
from cooldown import extract_cooldown_from_page

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 5
FAILURE_COOLDOWN_SECONDS = 1800  # 30 minutes
CDP_PORT = 9222


def find_chrome_path() -> str:
    """Find Chrome executable on Windows."""
    possible_paths = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return "chrome"  # Hope it's in PATH


def launch_chrome(config: Config) -> subprocess.Popen:
    """Launch Chrome with remote debugging enabled (not as automated)."""
    chrome_path = find_chrome_path()
    profile_dir = str(Path("state/chrome_debug_profile").absolute())
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome_path,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "about:blank",
    ]

    logger.info("Launching Chrome: %s", " ".join(cmd))
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)  # Wait for Chrome to start
    return process


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
    logger.info("URL: %s", config.base_url)

    # Ensure runtime directories exist
    Path("state").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    # Launch a real Chrome process (not controlled by Playwright launcher)
    # This Chrome is NOT marked as automated - Cloudflare can't detect it
    chrome_process = launch_chrome(config)
    logger.info("Chrome process started (PID: %d)", chrome_process.pid)

    consecutive_failures = 0

    try:
        async with async_playwright() as pw:
            # Connect to the already-running Chrome via CDP
            # This is the key: Chrome was launched normally, not by Playwright
            browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            logger.info("Connected to Chrome via CDP")

            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()

            logger.info("Starting vote loop...")

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
            await browser.close()

    finally:
        # Kill Chrome process
        chrome_process.terminate()
        logger.info("Chrome process terminated. Bot shutdown complete.")


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
