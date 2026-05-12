import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_USER_DATA_DIR = Path("./user_data")
DEFAULT_DB_PATH = DEFAULT_USER_DATA_DIR / "vmarket.sqlite"


def get_db_path() -> Path:
    raw = os.environ.get("VMARKET_DB_PATH", str(DEFAULT_DB_PATH))
    return Path(raw).expanduser()


def get_user_data_dir() -> Path:
    raw = os.environ.get("VMARKET_USER_DATA_DIR", str(DEFAULT_USER_DATA_DIR))
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
