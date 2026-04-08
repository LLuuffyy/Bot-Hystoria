import logging
import re

from playwright.async_api import Page

logger = logging.getLogger(__name__)


def parse_cooldown(text: str) -> int | None:
    """Parse cooldown text like '1h 01m 32s' and return total seconds."""
    match = re.search(r"(\d+)\s*h\s*(\d+)\s*m\s*(\d+)\s*s", text)
    if not match:
        # Try minutes + seconds only (e.g. "15m 32s")
        match = re.search(r"(\d+)\s*m\s*(\d+)\s*s", text)
        if match:
            minutes, seconds = int(match.group(1)), int(match.group(2))
            return minutes * 60 + seconds
        return None

    hours, minutes, seconds = int(match.group(1)), int(match.group(2)), int(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


async def extract_cooldown_from_page(page: Page) -> int | None:
    """Extract cooldown remaining seconds from the vote page."""
    try:
        # Look for the countdown timer element
        timer = page.locator("text=/\\d+h\\s*\\d+m\\s*\\d+s/").first
        if await timer.is_visible(timeout=3000):
            text = await timer.text_content()
            if text:
                remaining = parse_cooldown(text)
                logger.debug("Cooldown parsed: %s -> %s seconds", text.strip(), remaining)
                return remaining
    except Exception:
        pass

    # Fallback: search the whole page text
    try:
        body_text = await page.text_content("body")
        if body_text:
            remaining = parse_cooldown(body_text)
            if remaining:
                logger.debug("Cooldown found in body text: %s seconds", remaining)
                return remaining
    except Exception:
        pass

    logger.warning("Could not extract cooldown from page")
    return None
