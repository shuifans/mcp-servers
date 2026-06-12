# mcp-servers

MCP (Model Context Protocol) Server 集合，用于搜索和阅读云服务商官方文档。基于阿里云 [IQS (Intelligent Query Service)](https://iqs.console.aliyun.com/) API 实现文档检索、全文读取和证据提取。

## 项目列表

| 项目 | 支持的云服务商 | 说明 |
|------|---------------|------|
| [aliyun-help-docs-mcp](./aliyun-help-docs-mcp/) | 阿里云 | 搜索和读取阿里云帮助文档 |
| [cloud-help-docs-mcp](./cloud-help-docs-mcp/) | 阿里云、火山引擎、腾讯云、AWS、Azure、GCP | 统一多云文档检索服务 |

## 工具概览

每个项目提供 3 个 MCP 工具：

| 工具 | 用途 |
|------|------|
| `search_cloud_docs` / `search_aliyun_docs` | 搜索云厂商帮助文档，返回候选 URL、标题和摘要 |
| `read_cloud_doc` / `read_aliyun_doc` | 读取单篇文档完整 Markdown 内容（带 SQLite 缓存） |
| `retrieve_cloud_docs` / `retrieve_aliyun_docs` | 端到端检索：搜索 → 读取 → 提取关键段落，返回可引用的 Evidence 对象 |

## 前置条件

- Python >= 3.10
- IQS API Key（[申请地址](https://iqs.console.aliyun.com/) | [API 文档](https://iqs.console.aliyun.com/overview)）

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/shuifans/mcp-servers.git
cd mcp-servers

# 2. 安装其中一个项目
cd cloud-help-docs-mcp  # 或 aliyun-help-docs-mcp
./install.sh

# 3. 按提示配置 IQS_API_KEY 并注册到 Claude Code
```

安装脚本会自动：
- 检查 Python 版本（需要 3.10+）
- 创建虚拟环境并安装依赖
- 生成 `.env` 配置文件模板

各项目独立安装，详见各自的 README：

- [aliyun-help-docs-mcp 安装说明](./aliyun-help-docs-mcp/README.md)
- [cloud-help-docs-mcp 安装说明](./cloud-help-docs-mcp/README.md)

## 传输方式

仅支持 **STDIO** 模式（客户端子进程方式），MCP Server 需安装在 Agent 客户端所在的机器上。

## License

Apache-2.0
