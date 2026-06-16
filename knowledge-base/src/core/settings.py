import json
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kb_root: Path = Path("~/Documents/KnowledgeBase")
    kb_data_dir: Path = Path("~/Documents/KnowledgeBase/.kb-data")
    temp_source_dirs: str = ""
    qdrant_url: str = "http://localhost:6333"
    embedding_model: str = "BAAI/bge-m3"
    embedding_enabled: bool = True
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-plus"
    dashscope_planner_model: str = ""  # 为空时使用 dashscope_model
    iqs_endpoint: str = ""
    iqs_api_key: str = ""
    iqs_engine_type: str = "LiteAdvanced"
    ata_base_url: str = "https://ata.atatech.org/"
    yunzhidao_base_url: str = "https://yunzhidao.alibaba-inc.com/doc/"
    internal_browser_profile: Path = Path("~/.local/share/mac-knowledge-base/browser-profile")
    max_context_chars: int = 16000
    max_file_size_mb: int = 50

    def prepare(self) -> None:
        self.kb_root = self.kb_root.expanduser()
        self.kb_data_dir = self.kb_data_dir.expanduser()
        self.internal_browser_profile = self.internal_browser_profile.expanduser()
        for path in [
            self.kb_root,
            *(self.kb_root / name for name in ("projects", "work", "learning", "archive")),
            self.kb_data_dir,
            self.internal_browser_profile,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    @property
    def internal_auth_state(self) -> Path:
        return self.kb_data_dir / "internal-auth-state.json"

    @property
    def source_dirs(self) -> list[Path]:
        extras = [Path(p.strip()).expanduser() for p in self.temp_source_dirs.split(",") if p.strip()]
        managed_file = self.kb_data_dir / "source_dirs.json"
        if managed_file.exists():
            extras.extend(Path(p).expanduser() for p in json.loads(managed_file.read_text()))
        return list(dict.fromkeys([self.kb_root, *extras]))


settings = Settings()
