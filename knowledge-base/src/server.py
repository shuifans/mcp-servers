"""知识库 MCP Server 入口"""
import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from src.config import settings
from src.core.db import Database
from src.core.directories import DirectoryManager
from src.core.indexer import FileIndexer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 MCP Server 实例
app = FastMCP("knowledge-base")

# --- 初始化核心组件 ---

# 确保数据目录存在
settings.kb_data_dir.mkdir(parents=True, exist_ok=True)

# 数据库
db = Database(settings.kb_data_dir / "knowledge.db")

# 目录管理
directory_manager = DirectoryManager(db)

# 索引器
indexer = FileIndexer(db, vector_store=None)

# --- 内网站点适配器（ATA + 云知道）---
ata_adapter = None
yunzhidao_adapter = None
try:
    from src.core.internal_sites import build_internal_sites

    internal_sites = build_internal_sites(settings, db, vector_store=None)
    ata_adapter = next((s for s in internal_sites if s.source_type == "ata"), None)
    yunzhidao_adapter = next((s for s in internal_sites if s.source_type == "yunzhidao"), None)
except Exception as e:
    logger.warning("内网站点适配器初始化失败（搜索功能不可用）: %s", e)

# --- 公网搜索 ---
iqs_provider = None
try:
    if settings.iqs_endpoint and settings.iqs_api_key:
        from src.core.public_search import IQSSearchProvider

        iqs_provider = IQSSearchProvider(
            endpoint=settings.iqs_endpoint,
            api_key=settings.iqs_api_key,
            engine_type=settings.iqs_engine_type,
        )
except Exception as e:
    logger.warning("公网搜索初始化失败: %s", e)

# --- 注册 Tools ---
from src.tools.local_search import register_local_search
from src.tools.manage import register_manage_tools

register_local_search(app, db)

if ata_adapter:
    try:
        from src.tools.ata_search import register_ata_search
        register_ata_search(app, ata_adapter)
    except Exception as e:
        logger.warning("ATA 搜索 tool 注册失败: %s", e)

if yunzhidao_adapter:
    try:
        from src.tools.yunzhidao_search import register_yunzhidao_search
        register_yunzhidao_search(app, yunzhidao_adapter)
    except Exception as e:
        logger.warning("云知道搜索 tool 注册失败: %s", e)

if iqs_provider:
    try:
        from src.tools.public_search import register_public_search
        register_public_search(app, iqs_provider)
    except Exception as e:
        logger.warning("公网搜索 tool 注册失败: %s", e)

register_manage_tools(app, db, indexer, directory_manager)


async def main() -> None:
    """启动 MCP Server（stdio transport）"""
    logger.info("Knowledge Base MCP Server starting...")
    logger.info("  KB Root: %s", settings.kb_root)
    logger.info("  DB: %s", settings.kb_data_dir / "knowledge.db")
    logger.info("  IQS: %s", "configured" if iqs_provider else "not configured")
    logger.info("  ATA: %s", "available" if ata_adapter else "not available")
    logger.info("  云知道: %s", "available" if yunzhidao_adapter else "not available")

    await app.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
