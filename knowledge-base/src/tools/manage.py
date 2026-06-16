"""索引管理 MCP Tools"""
import subprocess
import sys
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.core.db import Database
from src.core.directories import DirectoryManager
from src.core.indexer import FileIndexer
from src.config import settings


def register_manage_tools(
    app: FastMCP,
    db: Database,
    indexer: FileIndexer,
    directory_manager: DirectoryManager,
):
    """注册管理类 tools"""

    _scan_state = {"running": False, "last_result": None, "error": None}

    @app.tool()
    async def internal_login() -> str:
        """启动浏览器完成 ATA/云知道 SSO 登录。

        会打开一个 Chrome 浏览器窗口，分别打开 ATA 和云知道的登录页面。
        请在浏览器中手动完成 SSO 登录（使用公司账号），两个站点都登录成功后浏览器会自动关闭。
        登录状态会持久化保存，后续搜索无需重复登录（直到 cookie 过期）。
        """
        try:
            project_root = Path(__file__).resolve().parent.parent.parent
            subprocess.Popen(
                [sys.executable, "-m", "src.core.browser_login"],
                cwd=str(project_root),
            )
            return (
                "浏览器已启动，请在打开的 Chrome 窗口中完成 ATA 和云知道的 SSO 登录。"
                "登录成功后浏览器将自动关闭。"
            )
        except Exception as e:
            return f"启动登录浏览器失败: {e}"

    @app.tool()
    async def scan_index() -> str:
        """触发本地知识库全量扫描（后台执行）。

        立即返回，扫描在后台进行。通过 index_status 查看扫描进度和结果。
        扫描所有已授权的目录，索引新增/修改的文档（PDF/DOCX/PPTX/XLSX/MD/TXT），
        移除已删除文件的索引。使用 SHA-256 去重，相同内容不会重复索引。
        """
        if _scan_state["running"]:
            return "⏳ 扫描正在进行中，请稍后通过 index_status 查看结果。"

        def _do_scan():
            _scan_state["running"] = True
            _scan_state["error"] = None
            try:
                roots = directory_manager.get_enabled_roots()
                result = indexer.scan(roots, directory_manager=directory_manager)
                _scan_state["last_result"] = result
            except Exception as e:
                _scan_state["error"] = str(e)
            finally:
                _scan_state["running"] = False

        threading.Thread(target=_do_scan, daemon=True).start()
        return "✅ 后台扫描已启动。请稍后调用 index_status 查看索引进度和结果。"

    @app.tool()
    async def manage_directory(path: str, action: str = "add") -> str:
        """管理授权索引目录。

        控制哪些目录被纳入本地知识库索引范围。
        添加目录后需调用 scan_index 来索引其中的文档。
        移除目录不会删除原始文件，仅从索引中移除。

        Args:
            path: 目录绝对路径（支持 ~ 表示 home 目录）
            action: 操作类型 - "add"(添加), "remove"(移除), "list"(列出所有)
        """
        if action == "list":
            dirs = directory_manager.list_directories()
            if not dirs:
                return "当前没有授权目录。使用 action='add' 添加目录。"
            lines = ["**授权目录列表：**\n"]
            for d in dirs:
                status = "启用" if d.enabled else "停用"
                lines.append(f"- `{d.path}` [{status}]")
            return "\n".join(lines)
        elif action == "add":
            try:
                config = directory_manager.add_directory(path)
                return f"已添加目录: `{config.path}`\n请调用 scan_index 来索引该目录中的文档。"
            except Exception as e:
                return f"添加失败: {e}"
        elif action == "remove":
            success = directory_manager.remove_directory(path)
            if success:
                return f"已移除目录: `{path}`（原始文件不受影响）"
            return f"未找到目录: `{path}`"
        else:
            return f"未知操作: {action}。支持: add, remove, list"

    @app.tool()
    async def index_status() -> str:
        """查看知识库索引状态。

        显示已索引的目录、文档数量、片段数量和最近扫描时间。
        """
        try:
            dirs = directory_manager.list_directories()
            with db.connect() as conn:
                doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

            lines = [
                "**知识库索引状态**\n",
                f"- 文档数: {doc_count}",
                f"- 片段数: {chunk_count}",
                f"- 授权目录: {len(dirs)} 个",
            ]

            if dirs:
                lines.append("\n**目录详情：**")
                for d in dirs:
                    status = directory_manager.get_scan_status(d.path)
                    status_str = ""
                    if status and status.last_scan_at:
                        status_str = f" (已索引 {status.indexed_files}/{status.total_files} 文件)"
                    lines.append(f"- `{d.path}`{status_str}")

            if _scan_state["running"]:
                lines.append("\n⏳ **扫描正在进行中...**")
            elif _scan_state["last_result"]:
                r = _scan_state["last_result"]
                lines.append(f"\n**上次扫描结果**: 扫描 {r['files_seen']} 文件, 新索引 {r['files_indexed']}, 错误 {len(r.get('errors', []))}")
            if _scan_state["error"]:
                lines.append(f"\n⚠️ **上次扫描错误**: {_scan_state['error']}")

            return "\n".join(lines)
        except Exception as e:
            return f"获取状态失败: {e}"
