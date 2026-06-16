import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .db import Database
from .parsers import SUPPORTED, chunk_parts, parse_file

if TYPE_CHECKING:
    from .directories import DirectoryManager


class FileIndexer:
    def __init__(self, db: Database, vector_store=None):
        self.db = db
        self.vector_store = vector_store

    def scan(self, roots: list[Path], directory_manager: "DirectoryManager | None" = None) -> dict:
        seen, indexed, errors = set(), 0, []
        per_root: dict[str, dict] = {}  # track per-root stats
        # 预先构建 root_key → embedding_enabled 映射（仅在提供 directory_manager 时）
        embedding_map: dict[str, bool] = {}
        if directory_manager is not None:
            for cfg in directory_manager.list_directories():
                embedding_map[str(Path(cfg.path).expanduser().resolve())] = cfg.embedding_enabled
        for root in roots:
            if not root.exists():
                continue
            root_key = str(root.resolve())
            root_embedding_enabled = embedding_map.get(root_key, False)
            root_seen, root_indexed, root_errors = 0, 0, []
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                # Apply directory manager filtering if available
                if directory_manager is not None:
                    if directory_manager.should_exclude(path, root_key):
                        continue
                    if not directory_manager.should_index_extension(path):
                        # Fall back to SUPPORTED set for code files etc.
                        if path.suffix.lower() not in SUPPORTED:
                            continue
                else:
                    if path.suffix.lower() not in SUPPORTED or ".kb-data" in path.parts:
                        continue
                resolved = str(path.resolve())
                seen.add(resolved)
                root_seen += 1
                stat = path.stat()
                if self.db.known_path(resolved, stat.st_mtime, stat.st_size):
                    continue
                try:
                    if self.index_file(path, embedding_enabled=root_embedding_enabled):
                        indexed += 1
                        root_indexed += 1
                except Exception as exc:
                    err_msg = f"{resolved}: {exc}"
                    errors.append(err_msg)
                    root_errors.append(err_msg)
            per_root[root_key] = {
                "total_files": root_seen,
                "indexed_files": root_indexed,
                "errors": root_errors,
            }
        self.db.remove_missing_paths(seen)
        # Update scan status for each root
        if directory_manager is not None:
            from .directories import ScanStatus

            now = datetime.now(timezone.utc).isoformat()
            for root_key, info in per_root.items():
                status = ScanStatus(
                    path=root_key,
                    total_files=info["total_files"],
                    indexed_files=info["indexed_files"],
                    errors=info["errors"],
                    last_scan_at=now,
                )
                directory_manager.update_scan_status(root_key, status)
        return {"files_seen": len(seen), "files_indexed": indexed, "errors": errors}

    def index_file(self, path: Path, embedding_enabled: bool = False) -> bool:
        raw = path.read_bytes()
        content_hash = hashlib.sha256(raw).hexdigest()
        stat = path.stat()
        existing = self.db.document_by_hash(content_hash)
        if existing:
            self.db.register_existing_path(existing, str(path.resolve()), stat.st_mtime, stat.st_size)
            return False
        document_id = content_hash
        parsed = chunk_parts(parse_file(path))
        now = datetime.now(timezone.utc).isoformat()
        chunks = [
            {
                "chunk_id": hashlib.sha256(f"{document_id}:{i}:{part.text}".encode()).hexdigest(),
                "document_id": document_id, "title": path.stem, "content": part.text,
                "source_type": "local_file", "path": str(path.resolve()), "url": None,
                "location": part.location,
            }
            for i, part in enumerate(parsed) if part.text.strip()
        ]
        self.db.replace_document(
            {"document_id": document_id, "title": path.stem, "source_type": "local_file", "content_hash": content_hash, "updated_at": now, "url": None},
            chunks,
            {"path": str(path.resolve()), "mtime": stat.st_mtime, "size": stat.st_size},
        )
        # 仅在该目录显式启用 embedding 且向量库可用时才向量化
        if (
            embedding_enabled
            and self.vector_store
            and getattr(self.vector_store, "enabled", False)
            and chunks
        ):
            self.vector_store.upsert(chunks)
        return True

