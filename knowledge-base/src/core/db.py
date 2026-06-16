import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .models import Location, SearchResult


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS documents (
  document_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  source_type TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  url TEXT
);
CREATE TABLE IF NOT EXISTS document_paths (
  document_id TEXT NOT NULL,
  path TEXT PRIMARY KEY,
  mtime REAL NOT NULL,
  size INTEGER NOT NULL,
  is_primary INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  source_type TEXT NOT NULL,
  path TEXT,
  url TEXT,
  location_json TEXT NOT NULL,
  FOREIGN KEY(document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED, title, content, tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT,
  status TEXT, files_seen INTEGER DEFAULT 0, files_indexed INTEGER DEFAULT 0, error TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question TEXT NOT NULL,
  answer_hash TEXT NOT NULL,
  useful INTEGER NOT NULL,
  comment TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def replace_document(self, document: dict, chunks: list[dict], path_info: dict | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO documents(document_id,title,source_type,content_hash,updated_at,url)
                VALUES(:document_id,:title,:source_type,:content_hash,:updated_at,:url)
                ON CONFLICT(document_id) DO UPDATE SET title=excluded.title,updated_at=excluded.updated_at,url=excluded.url""",
                document,
            )
            if path_info:
                old = conn.execute("SELECT document_id FROM document_paths WHERE path=?", (path_info["path"],)).fetchone()
                conn.execute("UPDATE document_paths SET is_primary=0 WHERE document_id=?", (document["document_id"],))
                conn.execute(
                    """INSERT INTO document_paths(document_id,path,mtime,size,is_primary) VALUES(?,?,?,?,1)
                    ON CONFLICT(path) DO UPDATE SET document_id=excluded.document_id,mtime=excluded.mtime,
                    size=excluded.size,is_primary=1""",
                    (document["document_id"], path_info["path"], path_info["mtime"], path_info["size"]),
                )
                if old and old["document_id"] != document["document_id"]:
                    self._delete_orphan(conn, old["document_id"])
            old_ids = [r["chunk_id"] for r in conn.execute("SELECT chunk_id FROM chunks WHERE document_id=?", (document["document_id"],))]
            conn.executemany("DELETE FROM chunks_fts WHERE chunk_id=?", [(x,) for x in old_ids])
            conn.execute("DELETE FROM chunks WHERE document_id=?", (document["document_id"],))
            for chunk in chunks:
                conn.execute(
                    """INSERT INTO chunks(chunk_id,document_id,title,content,source_type,path,url,location_json)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        chunk["chunk_id"], chunk["document_id"], chunk["title"], chunk["content"],
                        chunk["source_type"], chunk.get("path"), chunk.get("url"),
                        json.dumps(chunk.get("location", {}), ensure_ascii=False),
                    ),
                )
                conn.execute("INSERT INTO chunks_fts(chunk_id,title,content) VALUES(?,?,?)", (chunk["chunk_id"], chunk["title"], chunk["content"]))

    def register_existing_path(self, document_id: str, path: str, mtime: float, size: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO document_paths(document_id,path,mtime,size,is_primary) VALUES(?,?,?,?,0)
                ON CONFLICT(path) DO UPDATE SET document_id=excluded.document_id,mtime=excluded.mtime,size=excluded.size""",
                (document_id, path, mtime, size),
            )

    def document_by_hash(self, content_hash: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT document_id FROM documents WHERE content_hash=?", (content_hash,)).fetchone()
            return row["document_id"] if row else None

    def known_path(self, path: str, mtime: float, size: int) -> bool:
        with self.connect() as conn:
            return conn.execute(
                "SELECT 1 FROM document_paths WHERE path=? AND mtime=? AND size=?", (path, mtime, size)
            ).fetchone() is not None

    def remove_missing_paths(self, existing: set[str]) -> None:
        with self.connect() as conn:
            rows = list(conn.execute("SELECT document_id,path FROM document_paths"))
            affected = {r["document_id"] for r in rows if r["path"] not in existing}
            conn.executemany("DELETE FROM document_paths WHERE path=?", [(r["path"],) for r in rows if r["path"] not in existing])
            for document_id in affected:
                remaining = conn.execute(
                    "SELECT path FROM document_paths WHERE document_id=? ORDER BY is_primary DESC,path LIMIT 1", (document_id,)
                ).fetchone()
                if remaining:
                    conn.execute("UPDATE chunks SET path=? WHERE document_id=?", (remaining["path"], document_id))
                else:
                    self._delete_orphan(conn, document_id)

    def search_fts(self, query: str, limit: int = 20, sources: list[str] | None = None) -> list[SearchResult]:
        terms = " OR ".join(f'"{word}"' for word in query.split() if word.strip())
        if not terms:
            return []
        source_clause = ""
        params: list = [terms]
        if sources:
            source_clause = f" AND c.source_type IN ({','.join('?' * len(sources))})"
            params.extend(sources)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT c.*, bm25(chunks_fts) AS rank FROM chunks_fts
                JOIN chunks c ON c.chunk_id=chunks_fts.chunk_id
                WHERE chunks_fts MATCH ? {source_clause} ORDER BY rank LIMIT ?""", params
            ).fetchall()
            if not rows:
                like_clause = ""
                like_params: list = [f"%{query}%", f"%{query}%"]
                if sources:
                    like_clause = f" AND source_type IN ({','.join('?' * len(sources))})"
                    like_params.extend(sources)
                like_params.append(limit)
                rows = conn.execute(
                    f"""SELECT *, 1.0 AS rank FROM chunks
                    WHERE (title LIKE ? OR content LIKE ?) {like_clause} LIMIT ?""", like_params
                ).fetchall()
        return [self._result(row, 1.0 / (1.0 + abs(row["rank"]))) for row in rows]

    def get_chunks(self, ids: list[str]) -> list[SearchResult]:
        if not ids:
            return []
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM chunks WHERE chunk_id IN ({','.join('?' * len(ids))})", ids).fetchall()
        by_id = {r["chunk_id"]: self._result(r, 0) for r in rows}
        return [by_id[x] for x in ids if x in by_id]

    def duplicates(self, document_id: str) -> list[str]:
        with self.connect() as conn:
            return [r["path"] for r in conn.execute("SELECT path FROM document_paths WHERE document_id=? ORDER BY path", (document_id,))]

    def primary_path(self, document_id: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT path FROM document_paths WHERE document_id=? ORDER BY is_primary DESC LIMIT 1", (document_id,)
            ).fetchone()
            return row["path"] if row else None

    def stats(self) -> dict:
        with self.connect() as conn:
            return {
                "documents": conn.execute("SELECT count(*) n FROM documents").fetchone()["n"],
                "chunks": conn.execute("SELECT count(*) n FROM chunks").fetchone()["n"],
                "paths": conn.execute("SELECT count(*) n FROM document_paths").fetchone()["n"],
            }

    def delete_documents_by_url_prefix(self, prefix: str) -> int:
        with self.connect() as conn:
            rows = list(conn.execute("SELECT document_id FROM documents WHERE url LIKE ?", (f"{prefix}%",)))
            for row in rows:
                ids = [x["chunk_id"] for x in conn.execute("SELECT chunk_id FROM chunks WHERE document_id=?", (row["document_id"],))]
                conn.executemany("DELETE FROM chunks_fts WHERE chunk_id=?", [(x,) for x in ids])
                conn.execute("DELETE FROM documents WHERE document_id=?", (row["document_id"],))
            return len(rows)

    @staticmethod
    def _result(row, score: float) -> SearchResult:
        return SearchResult(
            chunk_id=row["chunk_id"], document_id=row["document_id"], title=row["title"],
            content=row["content"], source_type=row["source_type"], path=row["path"], url=row["url"],
            location=Location(**json.loads(row["location_json"])), score=score,
        )

    @staticmethod
    def _delete_orphan(conn, document_id: str) -> None:
        if conn.execute("SELECT 1 FROM document_paths WHERE document_id=? LIMIT 1", (document_id,)).fetchone():
            return
        ids = [r["chunk_id"] for r in conn.execute("SELECT chunk_id FROM chunks WHERE document_id=?", (document_id,))]
        conn.executemany("DELETE FROM chunks_fts WHERE chunk_id=?", [(x,) for x in ids])
        conn.execute("DELETE FROM documents WHERE document_id=? AND source_type='local_file'", (document_id,))
