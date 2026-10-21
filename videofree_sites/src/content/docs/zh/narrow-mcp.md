---
title: 窄 MCP 封装
lead: 网关的完整 MCP 有三十多个工具，覆盖全部工作台能力。跑一条全自动流水线时，你往往只需要提交、等待、取结果三件事——把工具面收窄到几个，Agent 上下文更小、更不容易走错路。这就是窄 MCP：基于网关 HTTP API，自己封装只含所需工具的小 MCP 服务。
order: 5
---

<div class="diagram">
  <div class="dtitle">full mcp vs narrow mcp</div>
  <div class="dstack">
    <div class="dbox"><b>完整 MCP（网关内置）</b><small>30+ 工具 · 项目管理 / 能力发现 / 导演协作 / 生成 / 插件动作 / 素材库 —— 适合通用助手</small></div>
    <div class="dbox hot"><b>窄 MCP（你自己封装）</b><small>3 个工具 · generate / wait / artifacts —— 全自动流水线专用</small></div>
    <div class="dbox"><b>共同底座：网关 HTTP API</b><small>http://127.0.0.1:8765/api/v2/* · x-api-token 认证</small></div>
  </div>
</div>

## <span class="no">1</span>什么时候需要窄 MCP

- **全自动流水线**：整条视频管线只用到固定几个动作，完整工具表纯属噪音；
- **降低出错率**：工具越少，Agent 选错工具、传错参数的概率越低；
- **加自己的合同**：窄层是你自己的代码——提交前校验、预算上限、强制项目 ID、写台账，都能塞进去。

窄 MCP 不替代网关，只是代理层：真实生成、任务队列、素材归档仍然全部由 VideoFree Studio 网关完成。

## <span class="no">2</span>两个可封装的接口面

| 接口面 | 地址 | 适合场景 |
| --- | --- | --- |
| HTTP REST | `http://127.0.0.1:8765/api/v2/*` | 挑几个端点封装窄 MCP，最常用 |
| MCP JSON-RPC | `POST /mcp` 的 `tools/call` | 直接复用完整工具表，加校验转发 |

两者共用工作台设置的同一个访问令牌：请求头 `x-api-token`。令牌为空时不需要认证。

<div class="diagram">
  <div class="dtitle">request path</div>
  <div class="dflow">
    <div class="dbox"><b>你的 Agent</b><small>只看到 3 个工具</small></div>
    <div class="darr"><span>→</span><small>MCP stdio</small></div>
    <div class="dbox hot"><b>窄 MCP Server</b><small>校验 · 台账 · 转发</small></div>
    <div class="darr"><span>→</span><small>HTTP + x-api-token</small></div>
    <div class="dbox"><b>VideoFree Studio 网关</b><small>/api/v2/*</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>ComfyUI</b><small>插件工作流</small></div>
  </div>
</div>

## <span class="no">3</span>三十行封装一个窄 MCP

安装官方 MCP SDK（`pip install "mcp[cli]"`），保存为 `narrow_mcp.py`：

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
    """提交一个生成任务，返回 job_id。capability_id 可通过 GET /api/v2/capabilities 查询。"""
    body = {"capability_id": capability_id, "prompt": prompt}
    if project_id:
        body["project_id"] = project_id
    return api("POST", "/api/v2/generations", body)

@mcp.tool()
def wait(job_id: str) -> dict:
    """最多等 30 秒，返回任务最新状态；未完成就再调一次。"""
    return api("GET", f"/api/v2/jobs/{job_id}/wait")

@mcp.tool()
def artifacts(job_id: str) -> dict:
    """任务完成后，取全部媒体产物 URL。"""
    return api("GET", f"/api/v2/jobs/{job_id}/artifacts")

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

常用端点还有：`GET /api/v2/capabilities`（能力发现）、`POST /api/v2/uploads`（参考素材）、`GET /api/v2/jobs/{id}/inputs`（核对任务实际用了哪些参考）、`POST /api/v2/jobs/{id}/cancel`。完整清单以运行中的网关为准。

## <span class="no">4</span>挂到 AI 客户端

在支持 MCP 的客户端里新增一个 stdio 服务：

```json
{
  "mcpServers": {
    "videofree-narrow": {
      "command": "python",
      "args": ["D:/mcp/narrow_mcp.py"],
      "env": { "VIDEOFREE_URL": "http://127.0.0.1:8765", "VIDEOFREE_API_TOKEN": "你的令牌" }
    }
  }
}
```

刷新工具列表，应该只看到 `generate`、`wait`、`artifacts` 三个工具。跑一轮「生成 → 等待 → 取产物」闭环即封装完成。

## <span class="no">5</span>在窄层加你自己的合同

窄 MCP 的价值不在转发，在校验。参考仓库里的生产级实现 [`examples/skills/dialogue-video-skill/scripts/guarded_mcp.py`](https://gitee.com/heroofgod_admin/videofreestudio/blob/master/examples/skills/dialogue-video-skill/scripts/guarded_mcp.py)——它走 `POST /mcp` 的 JSON-RPC `tools/call`，在每次提交前：

1. **校验参数合同**：能力 ID、分辨率、时长必须在预先批准的范围内，超预算直接拒绝；
2. **写提交台账**：每次请求的参数、回执、文件哈希追加到 `jobs.jsonl`，恢复时不重复提交已完成任务；
3. **幂等键防重**：提交携带 `idempotency_key`，网络重试不会重复扣显存抽卡。

::note
校验脚本只能拦住走窄层的请求，不能物理阻止 Agent 绕过它直连网关。宿主客户端仍应把工具白名单收紧到只有你的窄 MCP。
::
