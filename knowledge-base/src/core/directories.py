"""授权目录管理模块"""
from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


# 默认排除规则
DEFAULT_EXCLUDE_PATTERNS = [
    ".git",
    "node_modules",
    "dist",
    "build",
    ".kb-data",
    "__pycache__",
    ".venv",
    ".env",
    "*.pyc",
    ".DS_Store",
]

# 默认索引格式
DEFAULT_INDEX_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt"}

# 文件大小上限 (MB)
DEFAULT_MAX_FILE_SIZE_MB = 50


class DirectoryConfig(BaseModel):
    path: str
    enabled: bool = True
    embedding_enabled: bool = False
    exclude_patterns: list[str] = []  # 额外排除规则（追加到默认规则上）
    added_at: str = ""  # ISO 时间戳


class ScanStatus(BaseModel):
    path: str
    total_files: int = 0
    indexed_files: int = 0
    errors: list[str] = []
    last_scan_at: str | None = None


class DirectoryManager:
    """管理授权目录的增删改查，配置持久化到 SQLite settings 表"""

    SETTINGS_KEY = "managed_directories"
    SCAN_STATUS_KEY = "directory_scan_status"

    def __init__(self, db):
        self.db = db

    # ─── 内部工具方法 ────────────────────────────────────────────────

    def _load_directories(self) -> list[DirectoryConfig]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (self.SETTINGS_KEY,)
            ).fetchone()
        if not row:
            return []
        return [DirectoryConfig(**d) for d in json.loads(row["value"])]

    def _save_directories(self, dirs: list[DirectoryConfig]) -> None:
        data = json.dumps(
            [d.model_dump() for d in dirs], ensure_ascii=False, indent=2
        )
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (self.SETTINGS_KEY, data),
            )

    def _load_scan_statuses(self) -> dict[str, ScanStatus]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (self.SCAN_STATUS_KEY,)
            ).fetchone()
        if not row:
            return {}
        raw = json.loads(row["value"])
        return {k: ScanStatus(**v) for k, v in raw.items()}

    def _save_scan_statuses(self, statuses: dict[str, ScanStatus]) -> None:
        data = json.dumps(
            {k: v.model_dump() for k, v in statuses.items()},
            ensure_ascii=False,
            indent=2,
        )
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (self.SCAN_STATUS_KEY, data),
            )

    # ─── 公共 API ──────────────────────────────────────────────────

    def list_directories(self) -> list[DirectoryConfig]:
        """列出所有授权目录"""
        return self._load_directories()

    def add_directory(self, path: str) -> DirectoryConfig:
        """添加授权目录"""
        resolved = str(Path(path).expanduser().resolve())
        dirs = self._load_directories()
        # 去重
        for d in dirs:
            if str(Path(d.path).expanduser().resolve()) == resolved:
                return d
        config = DirectoryConfig(
            path=resolved,
            enabled=True,
            embedding_enabled=False,
            exclude_patterns=[],
            added_at=datetime.now(timezone.utc).isoformat(),
        )
        dirs.append(config)
        self._save_directories(dirs)
        return config

    def remove_directory(self, path: str) -> bool:
        """移除授权目录（不删除原文件）"""
        resolved = str(Path(path).expanduser().resolve())
        dirs = self._load_directories()
        new_dirs = [
            d
            for d in dirs
            if str(Path(d.path).expanduser().resolve()) != resolved
        ]
        if len(new_dirs) == len(dirs):
            return False
        self._save_directories(new_dirs)
        # 同时移除扫描状态
        statuses = self._load_scan_statuses()
        statuses.pop(resolved, None)
        self._save_scan_statuses(statuses)
        return True

    def update_directory(
        self,
        path: str,
        enabled: bool | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> DirectoryConfig | None:
        """更新目录配置"""
        resolved = str(Path(path).expanduser().resolve())
        dirs = self._load_directories()
        for d in dirs:
            if str(Path(d.path).expanduser().resolve()) == resolved:
                if enabled is not None:
                    d.enabled = enabled
                if exclude_patterns is not None:
                    d.exclude_patterns = exclude_patterns
                self._save_directories(dirs)
                return d
        return None

    def get_enabled_roots(self) -> list[Path]:
        """获取所有已启用的目录路径"""
        from .settings import settings

        roots: list[Path] = [settings.kb_root]
        # 保留 TEMP_SOURCE_DIRS 兼容
        extras = [
            Path(p.strip()).expanduser()
            for p in settings.temp_source_dirs.split(",")
            if p.strip()
        ]
        roots.extend(extras)
        # 添加 managed directories 中启用的
        for d in self._load_directories():
            if d.enabled:
                p = Path(d.path).expanduser().resolve()
                if p not in roots:
                    roots.append(p)
        return list(dict.fromkeys(roots))

    def get_scan_status(self, path: str) -> ScanStatus | None:
        """获取目录扫描状态"""
        resolved = str(Path(path).expanduser().resolve())
        statuses = self._load_scan_statuses()
        return statuses.get(resolved)

    def update_scan_status(self, path: str, status: ScanStatus) -> None:
        """更新扫描状态"""
        resolved = str(Path(path).expanduser().resolve())
        statuses = self._load_scan_statuses()
        statuses[resolved] = status
        self._save_scan_statuses(statuses)

    def should_exclude(self, file_path: Path, directory_path: str) -> bool:
        """检查文件是否应被排除"""
        # 检查隐藏目录（名称以.开头的目录组件）
        for part in file_path.parts:
            if part.startswith(".") and part != ".":
                return True

        name = file_path.name

        # 检查默认排除规则
        for pattern in DEFAULT_EXCLUDE_PATTERNS:
            if fnmatch.fnmatch(name, pattern):
                return True
            # 也检查路径中的目录名
            if pattern in file_path.parts:
                return True

        # 检查目录自定义排除模式
        resolved = str(Path(directory_path).expanduser().resolve())
        dirs = self._load_directories()
        for d in dirs:
            if str(Path(d.path).expanduser().resolve()) == resolved:
                for pattern in d.exclude_patterns:
                    if fnmatch.fnmatch(name, pattern):
                        return True
                    if pattern in file_path.parts:
                        return True
                break

        # 检查文件大小
        try:
            from .settings import settings

            max_size = settings.max_file_size_mb * 1024 * 1024
            if file_path.exists() and file_path.stat().st_size > max_size:
                return True
        except Exception:
            pass

        return False

    def should_index_extension(self, file_path: Path) -> bool:
        """检查文件扩展名是否在索引范围内"""
        return file_path.suffix.lower() in DEFAULT_INDEX_EXTENSIONS
