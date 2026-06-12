"""Configuration loaded from environment variables.

All sensitive values (API keys, URLs, etc.) MUST come from environment
variables. ``.env`` files are loaded best-effort via ``python-dotenv``.
No real secrets are ever written to source.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


def _env_str(key: str, default: str) -> str:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _env_list(key: str, default: list[str]) -> list[str]:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    """Runtime configuration for ``aliyun-help-docs-mcp``."""

    iqs_api_key: str = ""
    iqs_base_url: str = "https://cloud-iqs.aliyuncs.com"
    doc_cache_path: str = "./data/cache/doc_cache.sqlite"
    doc_cache_ttl_hours: int = 24
    url_whitelist: list[str] = field(
        default_factory=lambda: ["help.aliyun.com", "www.alibabacloud.com/help"]
    )
    log_level: str = "INFO"

    # Cache tuning
    cache_max_entries: int = 10000
    cache_busy_timeout_ms: int = 5000

    # IQS HTTP defaults
    iqs_search_path: str = "/search/unified"
    iqs_read_page_path: str = "/readpage/basic"
    iqs_scrape_page_path: str = "/readpage/scrape"

    iqs_search_timeout_s: float = 10.0
    iqs_read_timeout_s: float = 15.0
    iqs_scrape_timeout_s: float = 20.0

    iqs_search_retries: int = 2
    iqs_read_retries: int = 1
    iqs_retry_backoff_s: float = 1.0

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            iqs_api_key=_env_str("IQS_API_KEY", ""),
            iqs_base_url=_env_str("IQS_BASE_URL", "https://cloud-iqs.aliyuncs.com"),
            doc_cache_path=_env_str("DOC_CACHE_PATH", "./data/cache/doc_cache.sqlite"),
            doc_cache_ttl_hours=_env_int("DOC_CACHE_TTL_HOURS", 24),
            url_whitelist=_env_list(
                "URL_WHITELIST", ["help.aliyun.com", "www.alibabacloud.com/help"]
            ),
            log_level=_env_str("LOG_LEVEL", "INFO").upper(),
        )

    @property
    def cache_path(self) -> Path:
        return Path(self.doc_cache_path).expanduser()

    def ensure_cache_dir(self) -> Path:
        path = self.cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Return a cached singleton config built from current environment."""

    cfg = Config.from_env()
    _configure_logging(cfg.log_level)
    return cfg


def _configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
