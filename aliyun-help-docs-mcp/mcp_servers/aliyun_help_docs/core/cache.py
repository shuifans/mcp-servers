"""SQLite-backed cache for fetched docs.

Schema:

.. code-block:: sql

    CREATE TABLE IF NOT EXISTS doc_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL UNIQUE,
        url_hash TEXT NOT NULL,
        title TEXT,
        content TEXT NOT NULL,
        content_format TEXT DEFAULT 'markdown',
        content_length INTEGER,
        fetched_via TEXT DEFAULT 'ReadPageBasic',
        cached_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        hit_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

The cache uses WAL mode and an LRU eviction policy when ``cache_max_entries``
is exceeded.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..config import Config, get_config

logger = logging.getLogger(__name__)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS doc_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    url_hash TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    content_format TEXT DEFAULT 'markdown',
    content_length INTEGER,
    fetched_via TEXT DEFAULT 'ReadPageBasic',
    cached_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    hit_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_doc_cache_url_hash ON doc_cache(url_hash);
CREATE INDEX IF NOT EXISTS idx_doc_cache_expires_at ON doc_cache(expires_at);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _from_iso(s: str) -> datetime:
    # Handle both naive and aware ISO strings.
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def normalize_url(url: str) -> str:
    """Normalize a URL for stable cache keys.

    Steps:
    - Lowercase scheme and host.
    - Drop fragment.
    - Sort query params.
    - Strip trailing slash from path (but keep root '/').
    """

    parsed = urlsplit(url.strip())
    scheme = (parsed.scheme or "").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


class DocCache:
    """Thread-safe SQLite cache for fetched docs."""

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or get_config()
        self._lock = threading.Lock()
        self._path: Path = self._config.ensure_cache_dir()
        self._conn = self._open_connection(self._path)
        self._init_schema()

    # ---- connection management -------------------------------------------------

    def _open_connection(self, path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(path),
            timeout=self._config.cache_busy_timeout_ms / 1000,
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage transactions manually
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={int(self._config.cache_busy_timeout_ms)}")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    # ---- public API ------------------------------------------------------------

    @staticmethod
    def normalize_url(url: str) -> str:
        return normalize_url(url)

    def is_expired(self, entry: dict[str, Any]) -> bool:
        expires_at = entry.get("expires_at")
        if not expires_at:
            return True
        try:
            return _from_iso(expires_at) <= _utcnow()
        except ValueError:
            return True

    def get_cached(self, url: str) -> dict[str, Any] | None:
        """Return a non-expired cache entry for ``url``, or ``None``.

        Increments ``hit_count`` and updates ``updated_at`` on hit (used by LRU).
        """

        norm = normalize_url(url)
        url_hash = _hash_url(norm)
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM doc_cache WHERE url_hash = ? AND url = ? LIMIT 1",
                (url_hash, norm),
            ).fetchone()
            if row is None:
                return None
            entry = dict(row)
            if self.is_expired(entry):
                logger.debug("cache expired for %s", norm)
                return None
            self._conn.execute(
                "UPDATE doc_cache SET hit_count = hit_count + 1, updated_at = datetime('now') WHERE id = ?",
                (entry["id"],),
            )
            entry["hit_count"] = int(entry.get("hit_count") or 0) + 1
            return entry

    def set_cached(
        self,
        url: str,
        title: str | None,
        content: str,
        content_format: str = "markdown",
        fetched_via: str = "ReadPageBasic",
        ttl_hours: int | None = None,
    ) -> dict[str, Any]:
        """Insert or replace a cache entry for ``url``."""

        norm = normalize_url(url)
        url_hash = _hash_url(norm)
        ttl = ttl_hours if ttl_hours is not None else self._config.doc_cache_ttl_hours
        now = _utcnow()
        expires_at = now + timedelta(hours=ttl)
        cached_at_iso = _to_iso(now)
        expires_at_iso = _to_iso(expires_at)
        content_length = len(content or "")

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO doc_cache (
                    url, url_hash, title, content, content_format,
                    content_length, fetched_via, cached_at, expires_at,
                    hit_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'), datetime('now'))
                ON CONFLICT(url) DO UPDATE SET
                    url_hash = excluded.url_hash,
                    title = excluded.title,
                    content = excluded.content,
                    content_format = excluded.content_format,
                    content_length = excluded.content_length,
                    fetched_via = excluded.fetched_via,
                    cached_at = excluded.cached_at,
                    expires_at = excluded.expires_at,
                    updated_at = datetime('now')
                """,
                (
                    norm,
                    url_hash,
                    title,
                    content,
                    content_format,
                    content_length,
                    fetched_via,
                    cached_at_iso,
                    expires_at_iso,
                ),
            )
            self._evict_lru_locked()
            row = self._conn.execute(
                "SELECT * FROM doc_cache WHERE url = ? LIMIT 1", (norm,)
            ).fetchone()
            return dict(row) if row else {}

    def purge_expired(self) -> int:
        """Delete all expired entries; return number of rows deleted."""

        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM doc_cache WHERE expires_at <= ?", (_to_iso(_utcnow()),)
            )
            return int(cur.rowcount or 0)

    # ---- internal --------------------------------------------------------------

    def _evict_lru_locked(self) -> None:
        max_entries = max(int(self._config.cache_max_entries or 0), 0)
        if max_entries <= 0:
            return
        count_row = self._conn.execute("SELECT COUNT(*) AS c FROM doc_cache").fetchone()
        count = int(count_row["c"]) if count_row else 0
        overflow = count - max_entries
        if overflow <= 0:
            return
        # Evict least-recently-updated entries first.
        self._conn.execute(
            """
            DELETE FROM doc_cache WHERE id IN (
                SELECT id FROM doc_cache
                ORDER BY updated_at ASC, hit_count ASC, id ASC
                LIMIT ?
            )
            """,
            (overflow,),
        )
