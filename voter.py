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

        # Wait for the page to fully render (JS-rendered content)
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

        # Detect page state using exact IDs from the HTML
        return await _detect_and_act(page, context, config)

    except Exception as e:
        logger.error("Error during vote attempt: %s", e)
        await _take_debug_screenshot(page)
        return VoteResult.ERROR


async def _detect_and_act(page: Page, context: BrowserContext, config: Config) -> VoteResult:
    """Detect the vote page state and act accordingly."""

    # Read the vote status from #voteStatusCard class
    status_card = page.locator("#voteStatusCard")
    try:
        card_class = await status_card.get_attribute("class", timeout=5000) or ""
    except Exception:
        card_class = ""

    # Read the title: <h4 id="voteStatusTitle">Vote Disponible !</h4>
    status_title = ""
    try:
        status_title = await page.locator("#voteStatusTitle").text_content(timeout=3000) or ""
    except Exception:
        pass

    logger.debug("Vote card class: '%s', title: '%s'", card_class, status_title)

    # --- COOLDOWN STATE ---
    if "cooldown" in card_class.lower() or "cooldown" in status_title.lower():
        logger.info("Vote is on cooldown (title: %s)", status_title)
        return VoteResult.COOLDOWN

    # Fallback: check for PATIENTE button
    try:
        patiente = page.locator("text=PATIENTE").first
        if await patiente.is_visible(timeout=1000):
            logger.info("Vote is on cooldown (PATIENTE button visible)")
            return VoteResult.COOLDOWN
    except Exception:
        pass

    # --- VOTE AVAILABLE STATE ---
    if "available" in card_class.lower() or "Disponible" in status_title:
        logger.info("Vote is available! (title: %s)", status_title)

        # Step 1: Click #btnGenerateOTP on play-hystoria.net
        # This opens serveur-prive.net in a new tab
        vote_btn = page.locator("#btnGenerateOTP")
        try:
            await vote_btn.wait_for(state="visible", timeout=5000)
        except Exception as e:
            logger.warning("Vote button #btnGenerateOTP not found: %s", e)
            await _take_debug_screenshot(page)
            return VoteResult.ERROR

        # Listen for new tab/popup before clicking
        logger.info("Clicking vote button (#btnGenerateOTP)...")
        async with context.expect_page(timeout=15000) as new_page_info:
            await vote_btn.click()

        # Step 2: Handle the external vote page (serveur-prive.net)
        try:
            external_page = await new_page_info.value
            logger.info("External vote tab opened: %s", external_page.url)

            await external_page.wait_for_load_state("networkidle", timeout=30000)
            await external_page.wait_for_timeout(2000)

            # Click "Je vote maintenant" button on serveur-prive.net
            vote_now_btn = (
                external_page.locator("text=Je vote maintenant")
                .or_(external_page.locator("a:has-text('Je vote maintenant')"))
                .or_(external_page.locator("button:has-text('Je vote maintenant')"))
            ).first

            try:
                await vote_now_btn.wait_for(state="visible", timeout=10000)
                logger.info("Clicking 'Je vote maintenant' on serveur-prive.net...")
                await vote_now_btn.click()

                # Wait for the vote to be processed on the external site
                await external_page.wait_for_load_state("networkidle", timeout=30000)
                await external_page.wait_for_timeout(3000)
                logger.info("External vote completed. Page: %s", external_page.url)

            except Exception as e:
                logger.warning("Could not click 'Je vote maintenant': %s", e)
                await _take_debug_screenshot(external_page, prefix="external")

            # Close the external tab
            await external_page.close()
            logger.info("External vote tab closed")

        except Exception as e:
            logger.warning("Error handling external vote page: %s", e)
            # Close any extra tabs
            for p in context.pages[1:]:
                await p.close()

        # Step 3: Back on play-hystoria.net - click #btnManualCheck if it appears
        await page.bring_to_front()
        await page.wait_for_timeout(2000)

        manual_btn = page.locator("#btnManualCheck")
        try:
            if await manual_btn.is_visible(timeout=5000):
                logger.info("Manual check button appeared, clicking #btnManualCheck...")
                await manual_btn.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                await page.wait_for_timeout(3000)
        except Exception:
            pass

        # Step 4: Verify success - check if status changed to cooldown
        try:
            new_title = await page.locator("#voteStatusTitle").text_content(timeout=5000) or ""
            new_class = await page.locator("#voteStatusCard").get_attribute("class", timeout=3000) or ""

            if "cooldown" in new_class.lower() or "cooldown" in new_title.lower():
                logger.info("Vote confirmed successful! Status: %s", new_title)
                await save_cookies(context, config)
                return VoteResult.SUCCESS
        except Exception:
            pass

        # Check for reward modal (#rewardModal)
        try:
            reward_modal = page.locator("#rewardModal")
            if await reward_modal.is_visible(timeout=3000):
                logger.info("Reward modal appeared - vote successful!")
                await save_cookies(context, config)
                return VoteResult.SUCCESS
        except Exception:
            pass

        # If we went through the whole flow, assume success
        logger.info("Vote flow completed - assuming success")
        await save_cookies(context, config)
        return VoteResult.SUCCESS

    # Unknown state
    logger.warning("Unknown vote state - card class: '%s', title: '%s'", card_class, status_title)
    await _take_debug_screenshot(page)
    return VoteResult.ERROR


async def _take_debug_screenshot(page: Page, prefix: str = "error") -> None:
    """Take a screenshot for debugging purposes."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"logs/{prefix}_{timestamp}.png"
        await page.screenshot(path=path)
        logger.info("Debug screenshot saved: %s", path)
    except Exception as e:
        logger.debug("Could not take screenshot: %s", e)
