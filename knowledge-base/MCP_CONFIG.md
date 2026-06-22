# MCP 配置

## Claude Code

```bash
claude mcp add knowledge-base -s user \
  -- uv run --directory ~/.claude/mcp-servers/knowledge-base python -m src.server
```

## .mcp.json

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

配置后在对话中输入：
- "查看索引状态" → 应调用 index_status 工具
- "搜索本地文档：AI提效" → 应调用 search_local 工具
