"""本地文档搜索 MCP Tool"""
from mcp.server import Server
from src.core.db import Database
from src.core.models import SearchResult
from src.config import settings


def format_results(results: list[SearchResult]) -> str:
    """将搜索结果格式化为 Markdown"""
    if not results:
        return "未找到匹配的文档。"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"### [{i}] {r.title}")
        if r.path:
            fname = r.path.split("/")[-1]
            source = f"📁 [{fname}](file://{r.path})"
        elif r.url:
            source = f"🔗 [{r.url}]({r.url})"
        else:
            source = "unknown"
        lines.append(f"**来源**: {source}")
        if r.location:
            loc_parts = []
            loc = r.location
            if loc.page: loc_parts.append(f"第{loc.page}页")
            if loc.slide: loc_parts.append(f"幻灯片{loc.slide}")
            if loc.sheet: loc_parts.append(f"工作表:{loc.sheet}")
            if loc.section: loc_parts.append(f"§{loc.section}")
            if loc_parts:
                lines.append(f"**位置**: {' / '.join(loc_parts)}")
        content_preview = r.content[:300] + "..." if len(r.content) > 300 else r.content
        lines.append(f"\n{content_preview}\n")
        lines.append("---")
    return "\n".join(lines)


def register_local_search(app: Server, db: Database):
    """注册本地搜索 tool 到 MCP Server"""

    @app.tool()
    async def search_local(query: str, limit: int = 10) -> str:
        """搜索本地知识库文档（PDF/DOCX/PPTX/XLSX/MD/TXT）。

        在已索引的本地授权目录中搜索文档，使用全文检索匹配。
        返回匹配的文档片段，含标题、内容摘要、文件路径和位置信息。

        Args:
            query: 搜索关键词（支持中英文，空格分隔多个关键词取 OR 逻辑）
            limit: 返回结果数量上限，默认10条
        """
        results = db.search_fts(query, limit, ["local_file"])
        return format_results(results)
