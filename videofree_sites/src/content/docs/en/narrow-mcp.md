---
title: Narrow MCP
lead: "The gateway's full MCP exposes 30+ tools covering the entire workspace. A fully automated pipeline usually needs three things — submit, wait, fetch. Narrow the tool surface to those few and your agent gets a smaller context and fewer wrong turns. That's a narrow MCP: your own tiny MCP server wrapping just the tools you need, built on the gateway's HTTP API."
order: 5
---

<div class="diagram">
  <div class="dtitle">full mcp vs narrow mcp</div>
  <div class="dstack">
    <div class="dbox"><b>Full MCP (built into the gateway)</b><small>30+ tools · projects / discovery / director collaboration / generation / plugin actions / library — for general assistants</small></div>
    <div class="dbox hot"><b>Narrow MCP (you wrap it)</b><small>3 tools · generate / wait / artifacts — purpose-built for one pipeline</small></div>
    <div class="dbox"><b>Shared base: the gateway HTTP API</b><small>http://127.0.0.1:8765/api/v2/* · x-api-token auth</small></div>
  </div>
</div>

## <span class="no">1</span>When you need a narrow MCP

- **Fully automated pipelines**: the whole video line uses a handful of actions; the full tool table is pure noise;
- **Fewer mistakes**: fewer tools means fewer wrong picks and malformed calls;
- **Your own contracts**: the narrow layer is your code — pre-submit validation, budget caps, forced project IDs, and ledgers all live here.

A narrow MCP never replaces the gateway; it is a proxy. Real generation, job queues, and asset archiving still belong to VideoFree Studio.

## <span class="no">2</span>Two surfaces to wrap

| Surface | Address | Best for |
| --- | --- | --- |
| HTTP REST | `http://127.0.0.1:8765/api/v2/*` | Picking a few endpoints into your own narrow MCP — the usual path |
| MCP JSON-RPC | `POST /mcp` → `tools/call` | Reusing the full tool table behind validation and forwarding |

Both share the same access token from workspace settings: the `x-api-token` request header. With an empty token, no auth is required.

<div class="diagram">
  <div class="dtitle">request path</div>
  <div class="dflow">
    <div class="dbox"><b>Your agent</b><small>sees only 3 tools</small></div>
    <div class="darr"><span>→</span><small>MCP stdio</small></div>
    <div class="dbox hot"><b>Narrow MCP server</b><small>validate · ledger · forward</small></div>
    <div class="darr"><span>→</span><small>HTTP + x-api-token</small></div>
    <div class="dbox"><b>VideoFree Studio gateway</b><small>/api/v2/*</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>ComfyUI</b><small>plugin workflows</small></div>
  </div>
</div>

## <span class="no">3</span>Thirty lines to a narrow MCP

Install the official SDK (`pip install "mcp[cli]"`) and save this as `narrow_mcp.py`:

```python
from mcp.server.fastmcp import FastMCP
import json, os, urllib.request

GATEWAY = os.environ.get("VIDEOFREE_URL", "http://127.0.0.1:8765")
TOKEN = os.environ.get("VIDEOFREE_API_TOKEN", "")
mcp = FastMCP("videofree-narrow")

def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GATEWAY + path, data=data, method=method,
        headers={"Content-Type": "application/json", "x-api-token": TOKEN})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}

@mcp.tool()
def generate(capability_id: str, prompt: str, project_id: str = "") -> dict:
    """Submit one generation job and return its job_id. Discover capability_id via GET /api/v2/capabilities."""
    body = {"capability_id": capability_id, "prompt": prompt}
    if project_id:
        body["project_id"] = project_id
    return api("POST", "/api/v2/generations", body)

@mcp.tool()
def wait(job_id: str) -> dict:
    """Wait up to 30 seconds and return the latest job status; call again if still running."""
    return api("GET", f"/api/v2/jobs/{job_id}/wait")

@mcp.tool()
def artifacts(job_id: str) -> dict:
    """Once finished, fetch every media artifact URL."""
    return api("GET", f"/api/v2/jobs/{job_id}/artifacts")

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Other handy endpoints: `GET /api/v2/capabilities` (discovery), `POST /api/v2/uploads` (reference assets), `GET /api/v2/jobs/{id}/inputs` (audit which references a job actually used), `POST /api/v2/jobs/{id}/cancel`. The running gateway is the source of truth for the full list.

## <span class="no">4</span>Hook it into your AI client

Add one stdio server in any MCP-capable client:

```json
{
  "mcpServers": {
    "videofree-narrow": {
      "command": "python",
      "args": ["C:/mcp/narrow_mcp.py"],
      "env": { "VIDEOFREE_URL": "http://127.0.0.1:8765", "VIDEOFREE_API_TOKEN": "your token" }
    }
  }
}
```

Refresh the tool list — you should see exactly `generate`, `wait`, and `artifacts`. One full round of "generate → wait → fetch artifacts" proves the wrapper works.

## <span class="no">5</span>Put your own contracts in the narrow layer

The value of a narrow MCP is validation, not forwarding. See the production-grade reference in the repository, [`examples/skills/dialogue-video-skill/scripts/guarded_mcp.py`](https://github.com/linpengishero/VideoFreeStudio/blob/main/examples/skills/dialogue-video-skill/scripts/guarded_mcp.py) — it calls `tools/call` on `POST /mcp` and, before every submission:

1. **Validates the parameter contract**: capability ID, resolution, and duration must fall inside pre-approved bounds; over-budget requests are refused outright;
2. **Writes a submission ledger**: every request's arguments, receipts, and file hashes append to `jobs.jsonl`, so recovery never resubmits finished jobs;
3. **Uses idempotency keys**: each submission carries an `idempotency_key`, so a network retry never burns a second generation.

::note
A validation script only guards requests that pass through it — it cannot physically stop an agent from calling the gateway directly. Keep the host client's tool allowlist narrowed to your own MCP server.
::
