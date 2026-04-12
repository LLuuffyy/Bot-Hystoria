import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

import nodriver as uc

from config import load_config
from logger_setup import setup_logging
from cooldown import parse_cooldown

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 5
FAILURE_COOLDOWN_SECONDS = 1800  # 30 minutes


async def wait_for_cloudflare(tab: uc.Tab) -> None:
    """Wait for Cloudflare challenge to resolve."""
    for _ in range(15):
        try:
            title = await tab.evaluate("document.title")
            url = tab.target.url or ""
            # Cloudflare challenge pages have specific titles
            if "instant" not in str(title).lower() and "attention" not in str(title).lower():
                if "challenge" not in url:
                    return
        except Exception:
            pass
        await asyncio.sleep(2)
    logger.warning("Cloudflare challenge may not have resolved")


async def is_logged_in(tab: uc.Tab) -> bool:
    """Check if user is logged in by looking for Mon Profil."""
    try:
        el = await tab.find("Mon Profil", timeout=5)
        return el is not None
    except Exception:
        return False


async def do_login(tab: uc.Tab, username: str, password: str, login_url: str) -> bool:
    """Log in to play-hystoria.net."""
    logger.info("Navigating to login page...")
    await tab.get(login_url)
    await asyncio.sleep(3)
    await wait_for_cloudflare(tab)

    if await is_logged_in(tab):
        logger.info("Already logged in!")
        return True

    logger.info("Logging in as %s...", username)
    try:
        # Find and fill username field
        username_field = await tab.select('input[name="username"]') or \
                         await tab.select('input[name="email"]') or \
                         await tab.select('input[type="email"]')
        if username_field:
            await username_field.clear_input()
            await username_field.send_keys(username)

        # Find and fill password field
        password_field = await tab.select('input[type="password"]')
        if password_field:
            await password_field.clear_input()
            await password_field.send_keys(password)

        # Click submit
        submit_btn = await tab.select('button[type="submit"]')
        if not submit_btn:
            submit_btn = await tab.find("Connexion", best_match=True)
        if submit_btn:
            await submit_btn.click()

        await asyncio.sleep(5)
        await wait_for_cloudflare(tab)

        if await is_logged_in(tab):
            logger.info("Login successful!")
            return True

        logger.error("Login failed")
        return False

    except Exception as e:
        logger.error("Login error: %s", e)
        return False


async def attempt_vote(tab: uc.Tab, vote_url: str) -> str:
    """Attempt to vote. Returns: 'success', 'cooldown', 'not_logged_in', 'error'."""
    logger.info("Navigating to vote page...")
    await tab.get(vote_url)
    await asyncio.sleep(3)
    await wait_for_cloudflare(tab)

    # Check login status
    if not await is_logged_in(tab):
        logger.warning("Not logged in")
        return "not_logged_in"

    await asyncio.sleep(2)

    # Check vote status via JavaScript (using exact IDs from the HTML)
    try:
        card_class = await tab.evaluate(
            'document.getElementById("voteStatusCard")?.className || ""'
        )
        status_title = await tab.evaluate(
            'document.getElementById("voteStatusTitle")?.textContent || ""'
        )
        logger.info("Vote status - class: '%s', title: '%s'", card_class, status_title)
    except Exception:
        card_class = ""
        status_title = ""

    # COOLDOWN
    if "cooldown" in str(card_class).lower() or "cooldown" in str(status_title).lower():
        logger.info("Vote is on cooldown")
        return "cooldown"

    # VOTE AVAILABLE
    if "available" in str(card_class).lower() or "Disponible" in str(status_title):
        logger.info("Vote is available! Clicking vote button...")

        try:
            # Click #btnGenerateOTP
            vote_btn = await tab.select("#btnGenerateOTP")
            if not vote_btn:
                vote_btn = await tab.find("VOTER MAINTENANT", best_match=True)
            if not vote_btn:
                logger.error("Vote button not found")
                return "error"

            await vote_btn.click()
            await asyncio.sleep(5)

            # Handle external vote page (serveur-prive.net opens in new tab)
            # Find the new tab
            browser = tab.browser
            external_tab = None
            for t in browser.tabs:
                if t != tab and "serveur-prive" in str(t.target.url or ""):
                    external_tab = t
                    break

            if external_tab:
                logger.info("External vote tab found: %s", external_tab.target.url)
                await asyncio.sleep(3)

                # Click "Je vote maintenant" on the external site
                try:
                    vote_now = await external_tab.find("Je vote maintenant", best_match=True)
                    if vote_now:
                        logger.info("Clicking 'Je vote maintenant'...")
                        await vote_now.click()
                        await asyncio.sleep(5)
                except Exception as e:
                    logger.warning("Error on external vote page: %s", e)

                # Close the external tab
                try:
                    await external_tab.close()
                except Exception:
                    pass
                logger.info("External tab closed")

            # Back to main tab - click manual check if visible
            await tab.bring_to_front()
            await asyncio.sleep(3)

            try:
                manual_btn = await tab.select("#btnManualCheck")
                if manual_btn:
                    is_visible = await tab.evaluate(
                        'document.getElementById("btnManualCheck")?.style.display !== "none"'
                    )
                    if is_visible:
                        logger.info("Clicking manual check button...")
                        await manual_btn.click()
                        await asyncio.sleep(5)
            except Exception:
                pass

            # Verify success
            try:
                new_title = await tab.evaluate(
                    'document.getElementById("voteStatusTitle")?.textContent || ""'
                )
                if "cooldown" in str(new_title).lower():
                    logger.info("Vote confirmed successful!")
                    return "success"
            except Exception:
                pass

            logger.info("Vote flow completed - assuming success")
            return "success"

        except Exception as e:
            logger.error("Vote error: %s", e)
            await take_screenshot(tab)
            return "error"

    logger.warning("Unknown vote state")
    await take_screenshot(tab)
    return "error"


async def get_cooldown_seconds(tab: uc.Tab) -> int | None:
    """Extract cooldown remaining seconds from the page."""
    try:
        body_text = await tab.evaluate("document.body?.textContent || ''")
        return parse_cooldown(str(body_text))
    except Exception:
        return None


async def take_screenshot(tab: uc.Tab) -> None:
    """Take a debug screenshot."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"logs/error_{timestamp}.png"
        await tab.save_screenshot(path)
        logger.info("Screenshot saved: %s", path)
    except Exception as e:
        logger.debug("Could not take screenshot: %s", e)


async def main() -> None:
    setup_logging()
    config = load_config()

    logger.info("=== Bot-Hystoria Auto-Voter ===")
    logger.info("User: %s", config.username)
    logger.info("Vote interval: %d minutes", config.vote_interval)
    logger.info("URL: %s", config.base_url)

    Path("state").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    profile_dir = str(Path("state/chrome_profile").absolute())
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    consecutive_failures = 0

    # Launch Chrome with nodriver (undetectable!)
    browser = await uc.start(
        user_data_dir=profile_dir,
        headless=config.headless,
    )

    logger.info("Chrome launched (undetected). Starting vote loop...")

    tab = await browser.get("about:blank")

    while True:
        try:
            # Ensure logged in
            await tab.get(config.base_url)
            await asyncio.sleep(3)
            await wait_for_cloudflare(tab)

            if not await is_logged_in(tab):
                logger.info("Not logged in. Attempting login...")
                logged_in = await do_login(tab, config.username, config.password, config.login_url)
                if not logged_in:
                    logger.error("Login failed. Retrying in 2 minutes...")
                    await asyncio.sleep(120)
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        logger.critical("%d failures. Pausing 30 min...", consecutive_failures)
                        await asyncio.sleep(FAILURE_COOLDOWN_SECONDS)
                        consecutive_failures = 0
                    continue

            # Attempt to vote
            result = await attempt_vote(tab, config.vote_url)

            if result == "success":
                consecutive_failures = 0
                logger.info("Vote successful! Next vote in %d minutes.", config.vote_interval)
                await asyncio.sleep(config.vote_interval * 60)

            elif result == "cooldown":
                consecutive_failures = 0
                remaining = await get_cooldown_seconds(tab)
                if remaining:
                    wait = remaining + 60
                    logger.info("Cooldown: %d min %d sec remaining.", wait // 60, wait % 60)
                else:
                    wait = config.vote_interval * 60
                    logger.info("Cooldown active. Waiting %d minutes.", config.vote_interval)
                await asyncio.sleep(wait)

            elif result == "not_logged_in":
                consecutive_failures += 1
                await asyncio.sleep(30)

            elif result == "error":
                consecutive_failures += 1
                logger.warning("Error (%d/%d). Retrying in 60s...",
                               consecutive_failures, MAX_CONSECUTIVE_FAILURES)
                await asyncio.sleep(60)

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.critical("%d failures. Pausing 30 min...", consecutive_failures)
                await asyncio.sleep(FAILURE_COOLDOWN_SECONDS)
                consecutive_failures = 0

        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
            break

        except Exception as e:
            consecutive_failures += 1
            logger.exception("Unexpected error: %s", e)
            await asyncio.sleep(120)

    browser.stop()
    logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    uc.loop().run_until_complete(main())
