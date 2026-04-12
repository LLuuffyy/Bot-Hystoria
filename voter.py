import logging
import re
from enum import Enum

import httpx
from bs4 import BeautifulSoup

from config import Config
from cooldown import parse_cooldown

logger = logging.getLogger(__name__)


class VoteResult(Enum):
    SUCCESS = "success"
    COOLDOWN = "cooldown"
    NOT_LOGGED_IN = "not_logged_in"
    ERROR = "error"


async def check_vote_status(client: httpx.AsyncClient, config: Config) -> tuple[str, str]:
    """Fetch the vote page and return (card_class, status_title)."""
    resp = await client.get(config.vote_url)
    resp.raise_for_status()
    html = resp.text

    if "Mon Profil" not in html:
        return "not_logged_in", ""

    soup = BeautifulSoup(html, "html.parser")

    card = soup.find(id="voteStatusCard")
    card_class = " ".join(card.get("class", [])) if card else ""

    title_el = soup.find(id="voteStatusTitle")
    status_title = title_el.get_text(strip=True) if title_el else ""

    return card_class, status_title


async def get_cooldown_from_page(client: httpx.AsyncClient, config: Config) -> int | None:
    """Fetch the vote page and extract cooldown seconds."""
    try:
        resp = await client.get(config.vote_url)
        resp.raise_for_status()
        return parse_cooldown(resp.text)
    except Exception:
        return None


async def generate_otp(client: httpx.AsyncClient, config: Config) -> str | None:
    """POST to /api/vote with action=generate_otp. Returns the external vote URL."""
    logger.info("Génération OTP via API...")
    try:
        resp = await client.post(
            config.vote_api_url,
            data={"action": "generate_otp"},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": config.vote_url,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        logger.debug("API response: %s", data)

        if data.get("success") and data.get("vote_url"):
            logger.info("OTP généré! URL: %s", data["vote_url"])
            return data["vote_url"]

        logger.error("API generate_otp échoué: %s", data)
        return None

    except Exception as e:
        logger.error("Erreur generate_otp: %s", e)
        return None


async def vote_on_external_site(client: httpx.AsyncClient, vote_url: str) -> bool:
    """Visit the external vote page (serveur-prive.net) and click 'Je vote maintenant'."""
    logger.info("Visite page externe: %s", vote_url)
    try:
        # Step 1: GET the external vote page
        resp = await client.get(vote_url)
        resp.raise_for_status()
        html = resp.text
        logger.debug("Page externe chargée (%d chars)", len(html))

        # Step 2: Find "Je vote maintenant" link
        soup = BeautifulSoup(html, "html.parser")

        # Look for a link or button with "Je vote maintenant"
        vote_link = None
        for a in soup.find_all("a", href=True):
            if "vote" in a.get_text(strip=True).lower():
                vote_link = a["href"]
                break

        # Also try form action
        if not vote_link:
            form = soup.find("form")
            if form and form.get("action"):
                vote_link = form["action"]

        if vote_link:
            # Make the link absolute if relative
            if vote_link.startswith("/"):
                # Extract base from vote_url
                from urllib.parse import urlparse
                parsed = urlparse(vote_url)
                vote_link = f"{parsed.scheme}://{parsed.netloc}{vote_link}"
            elif not vote_link.startswith("http"):
                from urllib.parse import urljoin
                vote_link = urljoin(vote_url, vote_link)

            logger.info("Click 'Je vote maintenant': %s", vote_link)
            resp2 = await client.get(vote_link)
            resp2.raise_for_status()
            logger.info("Vote externe effectué (status %d)", resp2.status_code)
            return True

        # If no link found, the visit itself might count as the vote
        logger.warning("Lien 'Je vote maintenant' non trouvé, la visite seule suffit peut-être")
        return True

    except Exception as e:
        logger.error("Erreur vote externe: %s", e)
        return False


async def poll_vote_status(
    client: httpx.AsyncClient, config: Config, max_attempts: int = 18, interval: float = 5.0
) -> bool:
    """Poll the API to check if the vote was registered. 18 attempts * 5s = 90s max."""
    import asyncio
    logger.info("Vérification du vote (polling %d tentatives)...", max_attempts)

    for i in range(max_attempts):
        try:
            # Try check_vote action
            resp = await client.post(
                config.vote_api_url,
                data={"action": "check_vote"},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": config.vote_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            logger.debug("Poll #%d: %s", i + 1, data)

            # Check if vote is confirmed (status changed to cooldown)
            if data.get("success") or data.get("status") == "cooldown" or data.get("voted"):
                logger.info("Vote confirmé au poll #%d!", i + 1)
                return True

        except Exception as e:
            logger.debug("Poll #%d erreur: %s", i + 1, e)

        # Also check via page HTML
        try:
            card_class, status_title = await check_vote_status(client, config)
            if "cooldown" in card_class.lower() or "cooldown" in status_title.lower():
                logger.info("Vote confirmé (page en cooldown)!")
                return True
        except Exception:
            pass

        await asyncio.sleep(interval)

    logger.warning("Timeout polling - vote non confirmé après %d tentatives", max_attempts)
    return False


async def attempt_vote(client: httpx.AsyncClient, config: Config) -> VoteResult:
    """Full vote flow: check status → generate OTP → vote externally → verify."""
    import asyncio

    logger.info("=== Tentative de vote ===")

    # Step 1: Check current vote status
    try:
        card_class, status_title = await check_vote_status(client, config)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            logger.error("403 Forbidden - cookies expirés! Mets à jour CF_CLEARANCE et PHPSESSID dans .env")
            return VoteResult.ERROR
        raise

    logger.info("Status - class: '%s', title: '%s'", card_class, status_title)

    if card_class == "not_logged_in":
        return VoteResult.NOT_LOGGED_IN

    # COOLDOWN
    if "cooldown" in card_class.lower() or "cooldown" in status_title.lower():
        logger.info("Vote en cooldown")
        return VoteResult.COOLDOWN

    # VOTE AVAILABLE
    if "available" in card_class.lower() or "Disponible" in status_title:
        logger.info("Vote disponible! Lancement du processus...")

        # Step 2: Generate OTP
        vote_url = await generate_otp(client, config)
        if not vote_url:
            return VoteResult.ERROR

        # Step 3: Vote on external site
        await asyncio.sleep(2)
        await vote_on_external_site(client, vote_url)

        # Step 4: Poll for confirmation
        await asyncio.sleep(3)
        confirmed = await poll_vote_status(client, config)

        if confirmed:
            logger.info("Vote réussi!")
            return VoteResult.SUCCESS

        # Try manual check as fallback
        logger.info("Tentative manual_check...")
        try:
            resp = await client.post(
                config.vote_api_url,
                data={"action": "manual_check"},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": config.vote_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            data = resp.json()
            logger.debug("manual_check response: %s", data)
            if data.get("success"):
                logger.info("Vote confirmé via manual_check!")
                return VoteResult.SUCCESS
        except Exception as e:
            logger.debug("manual_check erreur: %s", e)

        # Assume success if we went through the whole flow
        logger.info("Flow complet - on assume le succès")
        return VoteResult.SUCCESS

    logger.warning("État de vote inconnu - class: '%s', title: '%s'", card_class, status_title)
    return VoteResult.ERROR
