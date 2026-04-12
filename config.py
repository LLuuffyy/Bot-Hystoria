import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    username: str
    password: str
    vote_interval: int  # minutes
    base_url: str
    cf_clearance: str
    phpsessid: str

    @property
    def login_url(self) -> str:
        return f"{self.base_url}/login"

    @property
    def vote_url(self) -> str:
        return f"{self.base_url}/vote"

    @property
    def vote_api_url(self) -> str:
        return f"{self.base_url}/api/vote"


def load_config() -> Config:
    username = os.getenv("HYSTORIA_USERNAME")
    password = os.getenv("HYSTORIA_PASSWORD")

    if not username or not password:
        print("ERREUR: HYSTORIA_USERNAME et HYSTORIA_PASSWORD doivent être définis dans .env")
        sys.exit(1)

    cf_clearance = os.getenv("CF_CLEARANCE", "")
    phpsessid = os.getenv("PHPSESSID", "")

    if not cf_clearance or not phpsessid:
        print("ERREUR: CF_CLEARANCE et PHPSESSID doivent être définis dans .env")
        print("Exporte-les depuis Chrome DevTools (F12 > Application > Cookies)")
        sys.exit(1)

    return Config(
        username=username,
        password=password,
        vote_interval=int(os.getenv("VOTE_INTERVAL_MINUTES", "90")),
        base_url=os.getenv("BASE_URL", "https://play-hystoria.net").rstrip("/"),
        cf_clearance=cf_clearance,
        phpsessid=phpsessid,
    )
