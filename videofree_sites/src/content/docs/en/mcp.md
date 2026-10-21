---
title: MCP Setup
lead: MCP lets any MCP-capable AI call VideoFree Studio directly for generation, queries, and project management. It starts with the gateway — no separate MCP service to run.
order: 4
---

<div class="diagram">
  <div class="dtitle">connection path</div>
  <div class="dflow">
    <div class="dbox"><b>AI client</b><small>MCP-capable</small></div>
    <div class="darr"><span>→</span><small>JSON-RPC</small></div>
    <div class="dbox hot"><b>/mcp</b><small>starts with the gateway</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>VideoFree Studio gateway</b><small>capabilities · projects · jobs</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>ComfyUI</b><small>plugin workflows</small></div>
  </div>
  <div class="dnote">a registered plugin shows up in list_capabilities automatically — zero extra MCP configuration</div>
</div>

## <span class="no">1</span>Confirm the gateway address

Start VideoFree Studio first. The default port is `8765` and the MCP path is fixed at `/mcp`.

- **Same machine**: use `http://127.0.0.1:8765/mcp`.
- **Another machine on the LAN**: replace `127.0.0.1` with the gateway machine's real LAN IP, e.g. `http://192.168.50.8:8765/mcp`. Never use `0.0.0.0`, and never change the path to `/sse`.

## <span class="no">2</span>Paste the client configuration

Add a server named `videofree` to your AI client's MCP configuration and paste the JSON below. Some clients require `type` to be `streamable-http` — follow your client's documentation.

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

Connecting from another machine only requires replacing the address with the gateway machine's IP:

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

## <span class="no">3</span>Add authentication when a token is set

The token is empty by default and no auth header is needed. If you configured a gateway access token in workspace Settings, add `headers` to the server configuration and replace the example value with your real token:

```json
{ "mcpServers": { "videofree": { "type": "http", "url": "http://127.0.0.1:8765/mcp", "headers": { "X-API-Token": "your-token" } } } }
```

::note
Never put tokens into public prompts, screenshots, or code repositories. The HTTP API and MCP share the same token from workspace Settings.
::

## <span class="no">4</span>Refresh tools and verify the connection

After saving, refresh the MCP tool list in your AI client. Have the AI call `get_health`, `list_capabilities`, and `list_voices` first — normal results mean the connection works.

The client must support HTTP POST with JSON responses. Legacy SSE-only clients cannot use this address directly; do not switch the path to `/sse`.

If the LAN connection fails, check the gateway bind address, the firewall, and that tokens match. A healthy gateway does not mean ComfyUI is connected — if generation fails, re-check the ComfyUI address in Settings.

## <span class="no">5</span>Need a smaller tool surface?

The full MCP exposes 30+ tools covering the entire workspace. For fully automated pipelines, you can wrap a narrow MCP containing just the few tools you need over the HTTP API — see [Narrow MCP](/en/guide/narrow-mcp/).
