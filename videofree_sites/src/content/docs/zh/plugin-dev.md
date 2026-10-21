---
title: 插件开发
lead: 开发插件本身也交给智能体：仓库自带开发 Skill，把调通的 ComfyUI 工作流交给它，分析、实现、测试一条龙。插件注册后，工作台用户和 MCP 里的 Agent 自动获得同一套能力，不需要为 MCP 写任何代码。
order: 3
---

<div class="diagram">
  <div class="dtitle">from workflow to mcp</div>
  <div class="dflow">
    <div class="dbox"><b>ComfyUI 工作流</b><small>已调通</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>插件目录</b><small>plugin.json 注册能力</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>网关扫描</b><small>重启即注册</small></div>
    <div class="darr">→</div>
    <div class="dbox hot"><b>工作台 + MCP 工具</b><small>自动出现，零接入代码</small></div>
  </div>
  <div class="dnote">list_capabilities 发现 · get_capability 查参数 · submit_generation 提交 —— 全部走通用工具</div>
</div>

## <span class="no">1</span>让开发智能体来做（推荐）

仓库已经提供 `.agents/skills/videofree-plugin-development/`。把完整目录安装到开发智能体（Claude Code、Codex、Trae 等）的技能目录，然后发送：

> 使用 $videofree-plugin-development，把我的 ComfyUI 工作流制作成 VideoFree Studio 插件。先分析输入、输出、模型依赖和插件形态，再实现、测试并运行发布自检；所有模型专用代码和资源必须留在插件目录。

智能体会先分析工作流、选对插件形态，再写实现、跑测试。下面的第 2–4 节是它每一步的依据，也是你验收的清单。

## <span class="no">2</span>选择插件形态

- **生成插件**：封装图片、视频、语音或音乐工作流；
- **动作插件**：提供二采、增强或业务操作；
- **项目小插件**：在当前项目或分类中管理剧本、进度等数据；
- **应用插件**：拥有完整独立页面，例如剪辑工具。

## <span class="no">3</span>把全部专用内容留在插件内部

插件的 `plugin.json` 是唯一注册入口。工作流、编译器、协作技能、Vue 页面、图标、预设和固定样本都必须随插件分发；不能把模型专用规则写进框架，也不能直接读取平台数据库或其他插件代码。

注册之后，MCP 接入是自动完成的：能力出现在 `list_capabilities` 里，Agent 用 `get_capability` 查输入限制、用 `submit_generation` 提交任务，全程不接触节点。你要做的只是把 `plugin.json` 的字段写对。

模型需要什么、装到哪里，写进插件自己的 `INSTALL.md`——这正是[插件安装](/guide/plugin-install/)里用户和智能体安装模型的唯一依据。

## <span class="no">4</span>按真实协议开发和验证

详细字段、运行时接口和 UI 规则以仓库中的 [`plugins/PLUGIN_DEVELOPMENT.md`](https://gitee.com/heroofgod_admin/videofreestudio/blob/master/plugins/PLUGIN_DEVELOPMENT.md)、[`docs/plugin-protocol.md`](https://gitee.com/heroofgod_admin/videofreestudio/blob/master/docs/plugin-protocol.md)、[`ARCHITECTURE.md`](https://gitee.com/heroofgod_admin/videofreestudio/blob/master/ARCHITECTURE.md) 为准。完成后至少验证插件扫描、相关测试、前端构建（有 UI 时）和 `videofree.bat --check`（Linux 使用 `./videofree.sh --check`）。

验证 MCP 侧是否注册成功：让任意支持 MCP 的 AI 调用一次 `list_capabilities`，你的新能力出现在列表里、`get_capability` 能返回完整输入 Schema，即接入完成。

::note
插件是可信本地代码，不是安全沙箱。安装或更新前先排空相关任务，更新后重启网关；插件不会自动替用户安装 ComfyUI 模型和节点。
::
