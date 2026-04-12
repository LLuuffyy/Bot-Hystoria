import logging
import re

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
