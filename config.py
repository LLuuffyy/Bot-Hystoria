import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    username: str
    password: str
    vote_interval: int  # minutes
    headless: bool
    base_url: str
    cookies_path: Path

    @property
    def login_url(self) -> str:
        return f"{self.base_url}/login"

    @property
    def vote_url(self) -> str:
        return f"{self.base_url}/vote"


def load_config() -> Config:
    username = os.getenv("HYSTORIA_USERNAME")
    password = os.getenv("HYSTORIA_PASSWORD")

    if not username or not password:
        print("ERREUR: HYSTORIA_USERNAME et HYSTORIA_PASSWORD doivent être définis dans .env")
        sys.exit(1)

    return Config(
        username=username,
        password=password,
        vote_interval=int(os.getenv("VOTE_INTERVAL_MINUTES", "90")),
        headless=os.getenv("HEADLESS", "true").lower() == "true",
        base_url=os.getenv("BASE_URL", "https://play-hystoria.net").rstrip("/"),
        cookies_path=Path("state/cookies.json"),
    )
