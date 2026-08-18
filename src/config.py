"""Central config: loads .env and exposes settings to the rest of the pipeline.

Keys are read here and nowhere else, so no other module needs to touch os.environ.
Values are never logged or printed - see mask() for the only safe way to show one.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

load_dotenv(PROJECT_ROOT / ".env")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip()
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct").strip()

ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()

# Kept for reference only. The FMP key carried over from DividendPredict returns 401
# on every endpoint including /v3/quote, so it is expired rather than tier-limited,
# and Phase 2 uses AlphaVantage instead.
FMP_API_KEY = os.getenv("FMP_API_KEY", "").strip()


class MissingKeyError(RuntimeError):
    """Raised when a required API key is absent. Never fall back to a placeholder."""


def mask(secret: str) -> str:
    """Render a key for logs without exposing it. Returns e.g. 'nvapi-...8f2c'."""
    if not secret:
        return "<missing>"
    if len(secret) <= 10:
        return "<set>"
    return f"{secret[:6]}...{secret[-4:]}"


def require_nvidia_key() -> str:
    if not NVIDIA_API_KEY or NVIDIA_API_KEY.startswith("nvapi-xxx"):
        raise MissingKeyError(
            "NVIDIA_API_KEY is not set in .env (or is still the placeholder from "
            ".env.example). Get a free key at https://build.nvidia.com and paste it "
            "into .env. Do not run with a fabricated key."
        )
    return NVIDIA_API_KEY


def require_alphavantage_key() -> str:
    if not ALPHAVANTAGE_API_KEY or ALPHAVANTAGE_API_KEY.startswith("xxx"):
        raise MissingKeyError(
            "ALPHAVANTAGE_API_KEY is not set in .env (or is still the placeholder from "
            ".env.example). Get a free key instantly at "
            "https://www.alphavantage.co/support/#api-key and paste it into .env. "
            "The public 'demo' key only works for a handful of sample symbols."
        )
    return ALPHAVANTAGE_API_KEY


def require_fmp_key() -> str:
    if not FMP_API_KEY or FMP_API_KEY.startswith("xxx"):
        raise MissingKeyError(
            "FMP_API_KEY is not set in .env (or is still the placeholder from "
            ".env.example). Sign up free at https://site.financialmodelingprep.com "
            "and paste the key into .env."
        )
    return FMP_API_KEY
