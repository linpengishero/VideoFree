---
title: MCP 接入
lead: MCP 是让支持 MCP 的 AI 直接调用 VideoFree Studio 生成、查询和管理项目的连接方式。它随网关一起启动，不需要另外运行 MCP 服务。
order: 4
---

<div class="diagram">
  <div class="dtitle">connection path</div>
  <div class="dflow">
    <div class="dbox"><b>AI 客户端</b><small>支持 MCP</small></div>
    <div class="darr"><span>→</span><small>JSON-RPC</small></div>
    <div class="dbox hot"><b>/mcp</b><small>随网关启动</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>VideoFree Studio 网关</b><small>能力 · 项目 · 任务</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>ComfyUI</b><small>插件工作流</small></div>
  </div>
  <div class="dnote">插件注册后自动出现在 list_capabilities，MCP 侧不需要任何额外配置</div>
</div>

## <span class="no">1</span>确认网关地址

先启动 VideoFree Studio。默认端口是 `8765`，MCP 地址固定为 `/mcp`。

- **同一台电脑**：使用 `http://127.0.0.1:8765/mcp`。
- **局域网其他电脑**：把 `127.0.0.1` 换成运行网关电脑的实际局域网 IP，例如 `http://192.168.50.8:8765/mcp`。不要填写 `0.0.0.0`，也不要把地址改成 `/sse`。

## <span class="no">2</span>粘贴客户端配置

在 AI 客户端的 MCP 服务配置中新增一个服务，名称填 `videofree`，然后粘贴下面的 JSON。不同客户端可能要求把 `type` 改成 `streamable-http`，以客户端文档为准。

```json
{
  "mcpServers": {
    "videofree": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

从另一台电脑连接时，只需要把 JSON 中的地址替换成网关电脑 IP：

```json
{
  "mcpServers": {
    "videofree": {
      "type": "http",
      "url": "http://192.168.50.8:8765/mcp"
    }
  }
}
```

## <span class="no">3</span>需要令牌时加入认证

默认令牌为空，不需要认证请求头。如果你在工作台设置中配置了网关访问令牌，在服务配置中加入 `headers`，并把示例值替换为真实令牌：

```json
{ "mcpServers": { "videofree": { "type": "http", "url": "http://127.0.0.1:8765/mcp", "headers": { "X-API-Token": "你的令牌" } } } }
```

::note
不要把令牌写进公开提示词、截图或代码仓库。HTTP API 和 MCP 共用工作台中的同一个令牌。
::

## <span class="no">4</span>刷新工具并验证连接

保存配置后刷新 AI 客户端的 MCP 工具列表。先让 AI 调用 `get_health`、`list_capabilities` 和 `list_voices`，能正常返回结果才表示连接完成。

客户端必须支持 HTTP POST 的 JSON 响应。旧版只支持 SSE 的客户端不能直接使用这个地址；不要把 MCP 地址改成 `/sse`。

如果局域网连接失败，检查网关监听地址、防火墙和令牌是否一致。网关在线不代表 ComfyUI 已连接，生成失败时再检查工作台里的 ComfyUI 地址。

## <span class="no">5</span>需要更小的工具面？

完整 MCP 有三十多个工具，覆盖全部工作台能力。跑全自动流水线时，可以基于 HTTP API 封装只包含所需几个工具的窄 MCP，见[窄 MCP 封装](/guide/narrow-mcp/)。
