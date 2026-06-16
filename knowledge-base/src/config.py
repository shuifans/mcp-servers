"""MCP Server 配置加载"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 知识库路径
    kb_root: Path = Path.home() / "Documents" / "KnowledgeBase"
    kb_data_dir: Path = Path.home() / "Documents" / "KnowledgeBase" / ".kb-data"

    # 公网搜索（阿里云 IQS）
    iqs_endpoint: str = ""
    iqs_api_key: str = ""
    iqs_engine_type: str = "LiteAdvanced"

    # 内网站点
    ata_base_url: str = "https://ata.atatech.org/"
    yunzhidao_base_url: str = "https://yunzhidao.alibaba-inc.com/doc/"
    internal_browser_profile: Path = (
        Path.home() / ".local" / "share" / "mac-knowledge-base" / "browser-profile"
    )

    # 文件大小上限
    max_file_size_mb: int = 50


settings = Settings()
