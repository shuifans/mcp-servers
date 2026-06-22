# knowledge-base

企业知识库 MCP Server — 搜索本地文档库 + 阿里内网（ATA/云知道）+ 公网优质来源，返回带出处的精准结果。

## 功能

提供 8 个 MCP 工具：

| 工具 | 用途 |
|------|------|
| `search_local` | 搜索本地已索引文档（PDF/DOCX/PPTX/XLSX/MD/TXT），全文检索匹配 |
| `search_ata` | 搜索 ATA 内部技术文档平台 |
| `search_yunzhidao` | 搜索云知道内部知识库 |
| `search_public` | 搜索公网优质来源（OpenAI/Anthropic/阿里云/AWS 等权威源） |
| `scan_index` | 触发本地知识库全量扫描（后台执行） |
| `manage_directory` | 管理授权索引目录（添加/移除/列出） |
| `index_status` | 查看知识库索引状态 |
| `internal_login` | 启动浏览器完成 ATA/云知道 SSO 登录 |

## 前置条件

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) 包管理器
- IQS API Key（[申请地址](https://iqs.console.aliyun.com/)）— 用于公网搜索和内网搜索

## 安装

```bash
cd ~/.claude/mcp-servers/knowledge-base
uv sync
```

首次使用 ATA/云知道搜索前，需调用 `internal_login` 工具完成 SSO 登录。

## 环境变量

在 `.env` 文件中配置（已包含在项目中，按需修改）：

| 变量 | 必需 | 说明 | 默认值 |
|------|------|------|--------|
| `KB_ROOT` | 是 | 本地知识库根目录 | `~/Documents/KnowledgeBase` |
| `IQS_API_KEY` | 是 | IQS 服务 API Key（公网搜索） | — |
| `IQS_ENDPOINT` | 否 | IQS 搜索端点 | `https://cloud-iqs.aliyuncs.com/search/unified` |
| `DASHSCOPE_API_KEY` | 否 | DashScope API Key（向量搜索，可选） | — |
| `EMBEDDING_ENABLED` | 否 | 是否启用向量搜索 | `false` |

## MCP 注册

### Claude Code

```bash
claude mcp add knowledge-base -s user \
  -- uv run --directory ~/.claude/mcp-servers/knowledge-base python -m src.server
```

### .mcp.json

```json
{
  "mcpServers": {
    "knowledge-base": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "~/.claude/mcp-servers/knowledge-base",
        "python",
        "-m",
        "src.server"
      ]
    }
  }
}
```

## 验证

配置完成后运行 `claude mcp list`，确认 `knowledge-base` 显示为 `Connected`。

测试命令：
- "查看索引状态" → 调用 `index_status`
- "搜索本地文档：AI提效" → 调用 `search_local`
- "搜索公网：Claude Code best practices" → 调用 `search_public`

## 项目结构

```
knowledge-base/
├── src/
│   ├── server.py              # MCP Server 入口 (STDIO)
│   ├── config.py              # 配置管理
│   ├── tools/
│   │   ├── local_search.py    # search_local
│   │   ├── ata_search.py      # search_ata
│   │   ├── yunzhidao_search.py # search_yunzhidao
│   │   ├── public_search.py   # search_public
│   │   └── manage.py          # scan_index / manage_directory / index_status
│   └── core/
│       ├── db.py              # SQLite 数据库
│       ├── indexer.py         # 文件索引器
│       ├── parsers.py         # 文档解析（PDF/DOCX/PPTX/XLSX）
│       ├── directories.py     # 目录管理
│       ├── browser_login.py   # SSO 登录
│       ├── internal_sites.py  # 内网站点适配器
│       ├── watcher.py         # 文件变更监听
│       └── settings.py        # 环境变量读取
├── pyproject.toml
├── .env
└── README.md
```

## License

Apache-2.0
