import logging

from playwright.async_api import Page, BrowserContext

from config import Config

logger = logging.getLogger(__name__)


async def wait_for_cloudflare(page: Page, timeout: int = 45000) -> None:
    """Wait for Cloudflare challenge to complete, clicking Turnstile if needed."""
    try:
        # Check if we're on a Cloudflare challenge page
        if "challenge" in page.url or "cdn-cgi" in page.url:
            logger.info("Cloudflare challenge detected, waiting...")

        # Try to click the Turnstile checkbox if present
        for _ in range(3):
            try:
                # Turnstile checkbox is inside an iframe
                cf_iframe = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
                checkbox = cf_iframe.locator("input[type='checkbox']").or_(
                    cf_iframe.locator(".cb-lb")
                ).or_(
                    cf_iframe.locator("#challenge-stage")
                )
                if await checkbox.first.is_visible(timeout=3000):
                    logger.info("Clicking Cloudflare Turnstile checkbox...")
                    await checkbox.first.click()
                    await page.wait_for_timeout(5000)
            except Exception:
                break

        # Wait for the challenge to resolve (page navigates away from challenge)
        await page.wait_for_function(
            """() => {
                return !document.querySelector('#challenge-running')
                    && !document.querySelector('#challenge-form')
                    && !document.querySelector('.cf-browser-verification')
                    && !document.title.includes('instant');
            }""",
            timeout=timeout,
        )
        logger.debug("Cloudflare challenge resolved")

    except Exception:
        pass  # No challenge present or already resolved


async def is_logged_in(page: Page) -> bool:
    """Check if the user is currently logged in."""
    try:
        profile_link = page.locator("text=Mon Profil").first
        return await profile_link.is_visible(timeout=3000)
    except Exception:
        return False


async def login(page: Page, context: BrowserContext, config: Config) -> bool:
    """Log in to play-hystoria.net. Returns True on success."""
    logger.info("Navigating to login page: %s", config.login_url)
    await page.goto(config.login_url, wait_until="networkidle", timeout=60000)
    await wait_for_cloudflare(page)

    # Check if already logged in
    if await is_logged_in(page):
        logger.info("Already logged in!")
        await save_cookies(context, config)
        return True

    logger.info("Logging in as %s...", config.username)

    try:
        # Fill login form
        username_field = (
            page.locator('input[name="username"]')
            .or_(page.locator('input[name="email"]'))
            .or_(page.locator('input[type="email"]'))
            .or_(page.locator('input[name="login"]'))
            .or_(page.get_by_placeholder("Nom d'utilisateur"))
            .or_(page.get_by_placeholder("Email"))
        ).first
        await username_field.fill(config.username, timeout=10000)

        password_field = page.locator('input[type="password"]').first
        await password_field.fill(config.password, timeout=10000)

        submit_btn = (
            page.locator('button[type="submit"]')
            .or_(page.get_by_role("button", name="Connexion"))
            .or_(page.get_by_role("button", name="Se connecter"))
            .or_(page.locator("button:has-text('Connexion')"))
        ).first
        await submit_btn.click(timeout=10000)

        # Wait for navigation after login
        await page.wait_for_load_state("networkidle", timeout=30000)
        await wait_for_cloudflare(page)

        # Verify login success
        if await is_logged_in(page):
            logger.info("Login successful!")
            await save_cookies(context, config)
            return True

        logger.error("Login failed - 'Mon Profil' not found after submission")
        return False

    except Exception as e:
        logger.error("Login error: %s", e)
        return False


async def save_cookies(context: BrowserContext, config: Config) -> None:
    """Save browser cookies/session to disk."""
    config.cookies_path.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(config.cookies_path))
    logger.debug("Cookies saved to %s", config.cookies_path)
