import logging

import httpx

from config import Config

logger = logging.getLogger(__name__)


def build_client(config: Config) -> httpx.AsyncClient:
    """Build an httpx client with the user's cookies and realistic headers."""
    cookies = httpx.Cookies()
    cookies.set("cf_clearance", config.cf_clearance, domain="play-hystoria.net")
    cookies.set("PHPSESSID", config.phpsessid, domain="play-hystoria.net")

    return httpx.AsyncClient(
        cookies=cookies,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": config.base_url + "/",
        },
        follow_redirects=True,
        timeout=30.0,
    )


async def check_session(client: httpx.AsyncClient, config: Config) -> bool:
    """Check if the current session is valid by looking for 'Mon Profil'."""
    try:
        resp = await client.get(config.base_url)
        resp.raise_for_status()
        if "Mon Profil" in resp.text:
            logger.info("Session valide (Mon Profil trouvé)")
            return True
        logger.warning("Session invalide (Mon Profil absent)")
        return False
    except httpx.HTTPStatusError as e:
        logger.error("Erreur HTTP session check: %s", e.response.status_code)
        return False
    except Exception as e:
        logger.error("Erreur session check: %s", e)
        return False


async def do_login(client: httpx.AsyncClient, config: Config) -> bool:
    """Attempt to log in via HTTP POST."""
    logger.info("Tentative de login HTTP pour %s...", config.username)
    try:
        # POST login form
        resp = await client.post(
            config.login_url,
            data={
                "username": config.username,
                "password": config.password,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": config.login_url,
            },
        )
        resp.raise_for_status()

        if "Mon Profil" in resp.text:
            logger.info("Login réussi!")
            return True

        logger.error("Login échoué - 'Mon Profil' absent après soumission")
        return False

    except Exception as e:
        logger.error("Erreur login: %s", e)
        return False
