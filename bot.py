import asyncio
import logging
from pathlib import Path

from config import load_config
from logger_setup import setup_logging
from auth import build_client, check_session, do_login
from voter import attempt_vote, get_cooldown_from_page, VoteResult

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 5
FAILURE_COOLDOWN_SECONDS = 1800  # 30 minutes


async def main() -> None:
    setup_logging()
    config = load_config()

    logger.info("=== Bot-Hystoria Auto-Voter (HTTP) ===")
    logger.info("User: %s", config.username)
    logger.info("Vote interval: %d minutes", config.vote_interval)
    logger.info("URL: %s", config.base_url)

    Path("logs").mkdir(exist_ok=True)

    client = build_client(config)
    consecutive_failures = 0

    # Check session on startup
    logger.info("Vérification de la session...")
    if not await check_session(client, config):
        logger.warning("Session invalide. Tentative de login...")
        if not await do_login(client, config):
            logger.error(
                "Login échoué. Vérifie que CF_CLEARANCE et PHPSESSID sont à jour dans .env"
            )
            logger.error(
                "Pour les mettre à jour : Chrome > F12 > Application > Cookies > play-hystoria.net"
            )
            await client.aclose()
            return

    logger.info("Session OK! Démarrage de la boucle de vote...")

    try:
        while True:
            try:
                # Re-check session
                if not await check_session(client, config):
                    logger.warning("Session expirée. Tentative de re-login...")
                    if not await do_login(client, config):
                        logger.error("Re-login échoué. Cookies probablement expirés.")
                        logger.error("Mets à jour CF_CLEARANCE et PHPSESSID dans .env et relance le bot.")
                        consecutive_failures += 1
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            logger.critical(
                                "%d échecs consécutifs. Arrêt du bot.", consecutive_failures
                            )
                            break
                        await asyncio.sleep(120)
                        continue

                # Attempt to vote
                result = await attempt_vote(client, config)

                if result == VoteResult.SUCCESS:
                    consecutive_failures = 0
                    logger.info(
                        "Vote réussi! Prochain vote dans %d minutes.", config.vote_interval
                    )
                    await asyncio.sleep(config.vote_interval * 60)

                elif result == VoteResult.COOLDOWN:
                    consecutive_failures = 0
                    remaining = await get_cooldown_from_page(client, config)
                    if remaining:
                        wait = remaining + 60  # +1 min buffer
                        logger.info(
                            "Cooldown: %d min %d sec restantes. Attente...",
                            wait // 60,
                            wait % 60,
                        )
                    else:
                        wait = config.vote_interval * 60
                        logger.info(
                            "Cooldown actif. Attente %d minutes.", config.vote_interval
                        )
                    await asyncio.sleep(wait)

                elif result == VoteResult.NOT_LOGGED_IN:
                    consecutive_failures += 1
                    logger.warning("Non connecté. Retry dans 30s...")
                    await asyncio.sleep(30)

                elif result == VoteResult.ERROR:
                    consecutive_failures += 1
                    logger.warning(
                        "Erreur (%d/%d). Retry dans 60s...",
                        consecutive_failures,
                        MAX_CONSECUTIVE_FAILURES,
                    )
                    await asyncio.sleep(60)

                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.critical(
                        "%d échecs consécutifs. Pause de 30 min...", consecutive_failures
                    )
                    await asyncio.sleep(FAILURE_COOLDOWN_SECONDS)
                    consecutive_failures = 0

            except KeyboardInterrupt:
                raise
            except Exception as e:
                consecutive_failures += 1
                logger.exception("Erreur inattendue: %s", e)
                await asyncio.sleep(120)

    except KeyboardInterrupt:
        logger.info("Bot arrêté par l'utilisateur.")
    finally:
        await client.aclose()
        logger.info("Bot shutdown terminé.")


if __name__ == "__main__":
    asyncio.run(main())
