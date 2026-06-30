# cloud-help-docs-mcp

统一的 MCP (Model Context Protocol) Server，支持搜索和阅读多家云服务商的官方文档。

## 支持的云服务商

| Provider | 值 | 文档站点 | 默认语言 |
|----------|-----|---------|---------|
| 阿里云 | `aliyun` | help.aliyun.com | 中文 |
| 火山引擎 | `volcengine` | www.volcengine.com/docs | 中文 |
| 腾讯云 | `tencent_cloud` | cloud.tencent.com/document | 中文 |
| AWS | `aws` | docs.aws.amazon.com | English |
| Azure | `azure` | learn.microsoft.com | English |
| GCP | `gcp` | cloud.google.com | English |

## 工具

### search_cloud_docs

搜索指定云服务商的官方文档，返回候选 URL 列表（含标题、摘要和相关度评分）。

```json
{
  "provider": "aws",
  "query": "EC2 launch instance",
  "product": "EC2",
  "top_k": 5
}
```

### read_cloud_doc

读取单个文档页面的完整内容（markdown 或 text），支持 SQLite 缓存和自动 scrape 回退。

```json
{
  "provider": "azure",
  "url": "https://learn.microsoft.com/en-us/azure/virtual-machines/overview",
  "force_refresh": false
}
```

### retrieve_cloud_docs

端到端检索：搜索 → 阅读 → 摘录，返回可引用的 Evidence 对象列表。

```json
{
  "provider": "gcp",
  "query": "BigQuery create dataset",
  "product": "BigQuery",
  "top_k_chunks": 5
}
```

## 快速开始

### 安装

依赖管理统一使用 [uv](https://docs.astral.sh/uv/)。先 `git clone` 本仓库，然后：

```bash
cd ~/.claude/mcp-servers/cloud-help-docs-mcp
./install.sh          # 内部执行 uv sync（自动创建 .venv 并按 uv.lock 安装）
```

或手动：

```bash
uv sync               # 仅运行时依赖
uv sync --extra dev   # 含测试/lint 工具
```

> 未安装 uv？`curl -LsSf https://astral.sh/uv/install.sh | sh` 或 `brew install uv`。

### 配置

`IQS_API_KEY` 推荐在 MCP 注册时通过 `-e` 传入（见下方「MCP 注册」），无需落盘。
如需本地直接运行，可复制 `.env.example` 为 `.env` 填入 key —— `.env` 已被 `.gitignore`
忽略，**切勿提交**：

```bash
cp .env.example .env
# 编辑 .env，设置 IQS_API_KEY
```

| 环境变量 | 必需 | 默认值 | 说明 |
|---------|------|--------|------|
| `IQS_API_KEY` | 是 | `""` | IQS API Bearer Token（[申请](https://iqs.console.aliyun.com/) / [API 文档](https://iqs.console.aliyun.com/overview)） |
| `IQS_BASE_URL` | 否 | `https://cloud-iqs.aliyuncs.com` | IQS 服务端点 |
| `CACHE_DIR` | 否 | `./data/cache` | 缓存目录（各 provider 独立 SQLite 文件） |
| `DOC_CACHE_TTL_HOURS` | 否 | `24` | 缓存有效期（小时） |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |

### 运行

```bash
uv run python -m mcp_servers.cloud_help_docs.server
# 或（激活环境后）
.venv/bin/cloud-help-docs-mcp
```

## MCP 注册

### Claude Code

```bash
claude mcp add cloud-help-docs-mcp -s user \
  -e IQS_API_KEY=<your_key> \
  -- ~/.claude/mcp-servers/cloud-help-docs-mcp/.venv/bin/python \
     -m mcp_servers.cloud_help_docs.server
```

### .mcp.json

> ⚠️ **安全提示**：切勿把真实 `IQS_API_KEY` 明文写进 `.mcp.json` 并提交到版本库。
> 下面的 `${IQS_API_KEY}` 会从当前 shell 环境读取，请先 `export IQS_API_KEY=<your_key>`
> （或写入不会被提交的本地 `.env`）。

```json
{
  "mcpServers": {
    "cloud-help-docs-mcp": {
      "type": "stdio",
      "command": "~/.claude/mcp-servers/cloud-help-docs-mcp/.venv/bin/python",
      "args": ["-m", "mcp_servers.cloud_help_docs.server"],
      "cwd": "~/.claude/mcp-servers/cloud-help-docs-mcp",
      "env": {
        "IQS_API_KEY": "${IQS_API_KEY}"
      }
    }
  }
}
```

## 架构

```
mcp_servers/cloud_help_docs/
├── config.py          # 环境变量配置
├── providers.py       # 6 个 provider 的注册表（site_filter / whitelist / cache / language）
├── server.py          # MCP Server 入口 (STDIO)
├── core/
│   ├── cache.py       # SQLite 缓存（TTL + LRU，按 provider 独立文件）
│   ├── evidence.py    # Evidence Pydantic 模型 + 摘录切片算法
│   ├── iqs_client.py  # IQS API 异步客户端（httpx）
│   └── url_whitelist.py # URL 白名单验证
├── tools/
│   ├── search.py      # search_cloud_docs
│   ├── read.py        # read_cloud_doc
│   └── retrieve.py    # retrieve_cloud_docs
└── schemas/           # JSON Schema 定义
```

### 搜索流程

1. **search_cloud_docs** → IQS UnifiedSearch（`site` 参数按 provider 切换）→ URL 白名单过滤 → 返回候选列表

> 白名单按 **host 精确匹配**（不含子域），这是有意的安全取舍：能防越权抓取，但也会过滤掉
> 区域子域（如 `repost.aws`、`xxx.help.aliyun.com`）。如需放行，请在 `providers.py` 的
> 对应 `whitelist` 中显式添加。
2. **read_cloud_doc** → URL 白名单验证 → SQLite 缓存检查 → IQS ReadPageBasic → Scrape 回退（< 200 字符时）→ 写入缓存
3. **retrieve_cloud_docs** → search + read（并发，Semaphore=4）→ EvidenceBuilder 摘录切片 → 返回 Evidence[]

### 添加新 Provider

只需在 `providers.py` 的 `PROVIDERS` 字典中添加一条记录：

```python
"new_provider": ProviderConfig(
    name="new_provider",
    display_name="New Provider",
    site_filter="docs.newprovider.com",
    whitelist=["docs.newprovider.com"],
    cache_filename="new_provider_doc_cache.sqlite",
    doc_language="en-US",
),
```

无需修改任何工具代码或 server.py。

## 依赖

- `mcp>=1.0.0` — MCP Python SDK
- `httpx>=0.27.0` — 异步 HTTP 客户端
- `pydantic>=2.6.0` — 数据验证
- `python-dotenv>=1.0.0` — `.env` 文件加载

## License

Apache-2.0
