# Qoder MCP 配置

在 Qoder 设置中添加以下 MCP Server 配置：

## 配置 JSON

```json
{
  "mcpServers": {
    "knowledge-base": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/judehuang/Documents/mcp-develop/knowledge-base", "python", "-m", "src.server"]
    }
  }
}
```

## 配置位置

Qoder → Settings → MCP Servers → 添加上述配置

## 验证

配置后在 Qoder 对话中输入：
- "查看索引状态" → 应调用 index_status 工具
- "搜索本地文档：AI提效" → 应调用 search_local 工具
