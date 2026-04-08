import logging
from datetime import datetime
from enum import Enum

from playwright.async_api import Page, BrowserContext

from config import Config
from auth import wait_for_cloudflare, save_cookies

logger = logging.getLogger(__name__)


class VoteResult(Enum):
    SUCCESS = "success"
    COOLDOWN = "cooldown"
    NOT_LOGGED_IN = "not_logged_in"
    ERROR = "error"


async def attempt_vote(page: Page, context: BrowserContext, config: Config) -> VoteResult:
    """Navigate to vote page and attempt to vote. Returns the result state."""
    logger.info("Navigating to vote page: %s", config.vote_url)

    try:
        await page.goto(config.vote_url, wait_until="networkidle", timeout=60000)
        await wait_for_cloudflare(page)

        # Wait a moment for the page to fully render (JS-rendered content)
        await page.wait_for_timeout(2000)

        # Check if we're redirected to login (not logged in)
        if "/login" in page.url:
            logger.warning("Redirected to login page - session expired")
            return VoteResult.NOT_LOGGED_IN

        # Check for "Mon Profil" to confirm we're logged in
        try:
            profile = page.locator("text=Mon Profil").first
            if not await profile.is_visible(timeout=5000):
                logger.warning("Not logged in - Mon Profil not visible")
                return VoteResult.NOT_LOGGED_IN
        except Exception:
            logger.warning("Could not verify login status")
            return VoteResult.NOT_LOGGED_IN

        # Detect page state: vote available or cooldown?
        return await _detect_and_act(page, context, config)

    except Exception as e:
        logger.error("Error during vote attempt: %s", e)
        await _take_debug_screenshot(page)
        return VoteResult.ERROR


async def _detect_and_act(page: Page, context: BrowserContext, config: Config) -> VoteResult:
    """Detect the vote page state and act accordingly."""

    # Check if cooldown is active
    cooldown_indicators = [
        page.locator("text=cooldown").first,
        page.locator("text=PATIENTE").first,
        page.locator("text=Patiente").first,
    ]
    for indicator in cooldown_indicators:
        try:
            if await indicator.is_visible(timeout=2000):
                logger.info("Vote is on cooldown")
                return VoteResult.COOLDOWN
        except Exception:
            continue

    # Look for the vote button
    vote_btn = (
        page.locator("button:has-text('VOTER')")
        .or_(page.locator("a:has-text('VOTER')"))
        .or_(page.locator("button:has-text('Voter')"))
        .or_(page.locator("a:has-text('Voter')"))
        .or_(page.get_by_role("button", name="VOTER"))
        .or_(page.get_by_role("link", name="VOTER"))
    ).first

    try:
        if await vote_btn.is_visible(timeout=5000):
            logger.info("Vote button found! Clicking...")
            await vote_btn.click()

            # Wait for the vote to be processed
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # Verify vote was successful by checking for cooldown state
            success_indicators = [
                page.locator("text=cooldown").first,
                page.locator("text=PATIENTE").first,
                page.locator("text=+50").first,
            ]
            for indicator in success_indicators:
                try:
                    if await indicator.is_visible(timeout=5000):
                        logger.info("Vote successful! Rewards earned.")
                        await save_cookies(context, config)
                        return VoteResult.SUCCESS
                except Exception:
                    continue

            # If we can't confirm success but no error, assume success
            logger.info("Vote clicked - assuming success (could not verify)")
            await save_cookies(context, config)
            return VoteResult.SUCCESS

    except Exception as e:
        logger.warning("Could not find or click vote button: %s", e)

    # If nothing matched, take a screenshot for debugging
    logger.warning("Unexpected page state - could not determine vote availability")
    await _take_debug_screenshot(page)
    return VoteResult.ERROR


async def _take_debug_screenshot(page: Page) -> None:
    """Take a screenshot for debugging purposes."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"logs/error_{timestamp}.png"
        await page.screenshot(path=path)
        logger.info("Debug screenshot saved: %s", path)
    except Exception as e:
        logger.debug("Could not take screenshot: %s", e)
