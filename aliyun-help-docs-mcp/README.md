# aliyun-help-docs-mcp

一个基于 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 的服务，用于搜索和读取阿里云官方帮助文档。通过阿里云 [IQS（Intelligent Query Service）](https://iqs.console.aliyun.com/) API 实现文档检索、全文读取和证据提取。

## 功能

提供 3 个 MCP 工具：

| 工具 | 用途 |
|------|------|
| `search_aliyun_docs` | 搜索阿里云帮助文档，返回候选 URL、标题和摘要 |
| `read_aliyun_doc` | 读取单篇文档的完整 Markdown 内容（带本地 SQLite 缓存） |
| `retrieve_aliyun_docs` | 端到端检索：搜索 → 读取 → 提取关键段落，返回可引用的 Evidence 对象 |

## 前置条件

- Python >= 3.10
- 阿里云 IQS API Key（[申请地址](https://iqs.console.aliyun.com/) | [API 文档](https://iqs.console.aliyun.com/overview)）

## 安装

```bash
cd ~/.claude/mcp-servers/aliyun-help-docs-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 环境变量

复制 `.env.example` 为 `.env` 并填入你的 API Key：

```bash
cp .env.example .env
```

| 变量 | 必需 | 说明 | 默认值 |
|------|------|------|--------|
| `IQS_API_KEY` | 是 | IQS 服务 API Key | — |
| `IQS_BASE_URL` | 否 | IQS 服务地址 | `https://cloud-iqs.aliyuncs.com` |
| `DOC_CACHE_PATH` | 否 | SQLite 缓存文件路径 | `./data/cache/doc_cache.sqlite` |
| `DOC_CACHE_TTL_HOURS` | 否 | 缓存过期时间（小时） | `24` |
| `URL_WHITELIST` | 否 | 允许读取的域名白名单（逗号分隔） | `help.aliyun.com,www.alibabacloud.com/help` |
| `LOG_LEVEL` | 否 | 日志级别 | `INFO` |

## 使用方式

### 接入方式说明

MCP 协议定义了三种客户端与服务端之间的传输方式：

| 传输方式 | 原理 | 是否需要部署到服务器 |
|---------|------|---------------------|
| **STDIO** | 客户端以子进程方式启动 MCP Server，通过标准输入/输出通信 | 否，本地运行 |
| **SSE** | MCP Server 作为 HTTP 服务暴露端点，客户端通过 Server-Sent Events 长连接通信 | 是 |
| **Streamable HTTP** | MCP 最新推荐的远程传输方式，基于 HTTP POST 请求 + 可选 SSE 流式响应 | 是 |

> **当前版本仅支持 STDIO 方式。** 这意味着 MCP Server 必须安装在与 Agent 客户端相同的机器上，由客户端直接拉起进程运行。如果你的 Agent 平台配置界面提供了 SSE 或 Streamable HTTP 选项，请不要选择——当前服务端尚未实现这两种传输协议的支持。

### 方式一：手动配置 MCP 服务（STDIO）

> 以下所有配置方式均为 STDIO 模式，要求本服务安装在 Agent 客户端所在的机器上。

#### Claude Code

运行以下命令注册（在项目目录下执行）：

```bash
claude mcp add aliyun-help-docs-mcp \
  -s user \
  -e IQS_API_KEY=<your-api-key> \
  -e IQS_BASE_URL=https://cloud-iqs.aliyuncs.com \
  -e DOC_CACHE_PATH=./data/cache/doc_cache.sqlite \
  -e "URL_WHITELIST=help.aliyun.com,www.alibabacloud.com/help" \
  -- ~/.claude/mcp-servers/aliyun-help-docs-mcp/.venv/bin/python -m mcp_servers.aliyun_help_docs.server
```

或者手动编辑项目根目录的 `.mcp.json`：

```json
{
  "mcpServers": {
    "aliyun-help-docs-mcp": {
      "type": "stdio",
      "command": "~/.claude/mcp-servers/aliyun-help-docs-mcp/.venv/bin/python",
      "args": ["-m", "mcp_servers.aliyun_help_docs.server"],
      "cwd": "~/.claude/mcp-servers/aliyun-help-docs-mcp",
      "env": {
        "IQS_API_KEY": "<your-api-key>",
        "IQS_BASE_URL": "https://cloud-iqs.aliyuncs.com",
        "DOC_CACHE_PATH": "./data/cache/doc_cache.sqlite",
        "URL_WHITELIST": "help.aliyun.com,www.alibabacloud.com/help"
      }
    }
  }
}
```

#### Cursor / Windsurf 等其他 MCP 客户端

在对应的 MCP 配置文件（如 `~/.cursor/mcp.json`）中添加相同的配置即可。

#### 通过 Agent 平台 UI 配置（百炼等）

如果你使用的 Agent 平台提供了 MCP 服务器的可视化配置界面，按以下方式填写：

| 配置项 | 值 |
|--------|------|
| **服务器类型** | **必须选择 `STDIO`**（不要选择 SSE 或 Streamable HTTP，当前版本不支持） |
| **命令** | `~/.claude/mcp-servers/aliyun-help-docs-mcp/.venv/bin/python -m mcp_servers.aliyun_help_docs.server` |
| **超时时间** | `60`（默认即可，网络较慢可设为 `120`） |

环境变量：

| Key | Value | 必需 |
|-----|-------|------|
| `IQS_API_KEY` | 你的 IQS API Key | 是 |
| `IQS_BASE_URL` | `https://cloud-iqs.aliyuncs.com` | 否 |
| `DOC_CACHE_PATH` | `~/.claude/mcp-servers/aliyun-help-docs-mcp/data/cache/doc_cache.sqlite` | 否 |
| `URL_WHITELIST` | `help.aliyun.com,www.alibabacloud.com/help` | 否 |

> **注意**：
> - 命令中必须使用虚拟环境的 Python **绝对路径**，不能使用系统 `python3`。
> - `DOC_CACHE_PATH` 建议使用绝对路径，避免 Agent 工作目录不同导致缓存路径错误。
> - STDIO 模式要求本服务安装在 Agent 平台所在的机器上，无法远程调用。

### 方式二：让 Agent 通过 Prompt 自行配置

将以下 Prompt 发送给 AI Agent（如 Claude Code），它会自动完成安装和注册：

```
请帮我配置 aliyun-help-docs-mcp 服务。

步骤：
1. 创建虚拟环境并安装依赖：
   cd ~/.claude/mcp-servers/aliyun-help-docs-mcp
   python3 -m venv .venv
   .venv/bin/pip install -e .
2. 注册为本地 MCP Server：
   claude mcp add aliyun-help-docs-mcp \
     -s user \
     -e IQS_API_KEY=<your-api-key> \
     -e IQS_BASE_URL=https://cloud-iqs.aliyuncs.com \
     -e DOC_CACHE_PATH=./data/cache/doc_cache.sqlite \
     -e "URL_WHITELIST=help.aliyun.com,www.alibabacloud.com/help" \
     -- ~/.claude/mcp-servers/aliyun-help-docs-mcp/.venv/bin/python -m mcp_servers.aliyun_help_docs.server

注意：command 必须使用虚拟环境中的 python 绝对路径，不能用系统 python。
```

## 验证

配置完成后，在 Claude Code 中输入 `/mcp` 查看服务状态，确认 `aliyun-help-docs-mcp` 显示为 `connected`。

然后直接用自然语言提问即可，例如：

- "帮我搜索阿里云 ECS 安全组配置的文档"
- "查一下 OSS 跨域设置的帮助文档"

## 项目结构

```
aliyun-help-docs-mcp/
├── mcp_servers/
│   └── aliyun_help_docs/
│       ├── __init__.py
│       ├── config.py          # 环境变量配置
│       ├── server.py          # MCP Server 入口
│       ├── core/
│       │   ├── cache.py       # SQLite 文档缓存
│       │   ├── evidence.py    # Evidence 对象构建
│       │   ├── iqs_client.py  # IQS HTTP 客户端
│       │   └── url_whitelist.py
│       ├── tools/
│       │   ├── search.py      # search_aliyun_docs
│       │   ├── read.py        # read_aliyun_doc
│       │   └── retrieve.py    # retrieve_aliyun_docs
│       └── schemas/           # JSON Schema 定义
├── data/cache/                # SQLite 缓存目录
├── pyproject.toml
├── .env.example
└── README.md
```

## License

Apache-2.0
