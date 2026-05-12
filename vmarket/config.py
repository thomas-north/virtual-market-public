import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get_db_path() -> Path:
    raw = os.environ.get("VMARKET_DB_PATH", "./data/vmarket.sqlite")
    return Path(raw).expanduser()


def get_base_currency() -> str:
    return os.environ.get("VMARKET_BASE_CURRENCY", "GBP").upper()


def get_alpha_vantage_key() -> str | None:
    key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    return key if key else None


def get_sec_user_agent() -> str:
    return os.environ.get(
        "VMARKET_SEC_USER_AGENT",
        "VirtualMarket/0.1 contact@example.com",
    )
