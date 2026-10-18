<script setup>
import { Icon } from "@iconify/vue";
import { ref } from "vue";
import PluginDialog from './PluginDialog.vue';

defineProps({ section: { type: String, default: "install" } });
defineEmits(["home", "enter", "section"]);

const contactOpen = ref(false);

const sagePrompt = "帮我给 ComfyUI 安装 SageAttention。先找到 ComfyUI 实际使用的 Python，检查显卡、Python、PyTorch 和 CUDA 版本，再选择兼容的安装方式。不要装到系统 Python，也不要未经确认升级 PyTorch 或 CUDA。安装后用这个 Python 验证能导入 sageattention。遇到不兼容先告诉我原因和方案。我的 ComfyUI 路径是：【填你的路径】。";
const installPrompt = "请帮我安装 videofree 的全自动视频技能。我已准备 dialogue-video-skill、openmontage 两个完整文件夹。先确认当前智能体的技能安装目录，再复制完整目录并保留所有资产、脚本和许可证。检查 Python 3.10+、FFmpeg 和 ffprobe，在你实际使用的 Python 环境安装 openmontage 的 requirements.txt。给主制片配置我的 videofree MCP：【填网关地址，例如 http://192.168.50.8:8765/mcp】。刷新技能发现，校验固定资产和媒体能力，只检查，不要直接生成或花费额度。";
const example = "使用 dialogue-video-skill，制作一段机器人和青年男人对话讲解的视频，主题是‘为什么天空是蓝色的’，30秒、9:16、保留对白、不加字幕。先告诉我制作方案、预计生成次数和是否二采，等我确认后再生成。";
</script>

<template>
  <div class="guide-page">
    <header class="guide-header">
      <button class="home-link" type="button" @click="$emit('home')"><Icon icon="solar:arrow-left-linear" width="18" /> videofree / 使用教程</button>
      <button class="enter-button" type="button" @click="$emit('enter')">进入工作台 <Icon icon="solar:arrow-right-linear" width="18" /></button>
    </header>
    <div class="guide-layout">
      <nav class="guide-nav" aria-label="教程板块">
        <span>开始使用</span>
        <button type="button" :class="{ active: section === 'install' }" :aria-current="section === 'install' ? 'page' : undefined" @click="$emit('section', 'install')">01 安装部署</button>
        <button type="button" :class="{ active: section === 'mcp' }" :aria-current="section === 'mcp' ? 'page' : undefined" @click="$emit('section', 'mcp')">02 MCP 安装</button>
        <button type="button" :class="{ active: section === 'skills' }" :aria-current="section === 'skills' ? 'page' : undefined" @click="$emit('section', 'skills')">03 全自动技能包</button>
        <button type="button" :class="{ active: section === 'plugin' }" :aria-current="section === 'plugin' ? 'page' : undefined" @click="$emit('section', 'plugin')">04 插件开发</button>
        <a href="https://pan.quark.cn/s/2d145a999169" target="_blank" rel="noopener noreferrer">配套整合包 <Icon icon="solar:arrow-right-up-linear" width="14" /></a>
        <small>夸克分享口令：2ca93bYCBE</small>
      </nav>
      <main :key="section" class="guide-content">
        <button class="installation-help" type="button" @click="contactOpen = true">
          <Icon icon="solar:chat-round-line-linear" width="22" />
          <span><strong>不会安装？联系我有偿安装</strong><small>点击查看微信二维码，咨询安装部署服务</small></span>
          <Icon icon="solar:arrow-right-linear" width="18" />
        </button>
        <template v-if="section === 'install'">
          <div class="eyebrow">板块一 / 从零开始</div>
          <h1>安装部署</h1>
          <p class="intro">ComfyUI 负责执行模型和节点，VideoFree 负责把复杂工作流变成可选择的插件能力，并统一管理提示词、任务和项目素材。两边都要启动，但使用内置能力时不需要再导入工作流或手工连接节点。</p>
          <section class="step">
            <h2><b>1</b>准备 ComfyUI、模型和插件</h2>
            <p>打开<a href="https://pan.quark.cn/s/2d145a999169" target="_blank" rel="noopener noreferrer">配套 ComfyUI 整合包</a>；也可以把完整口令 <code>/~2ca93bYCBE~:/</code> 复制到夸克 APP。里面提供项目需要的 ComfyUI、模型和插件。</p>
            <p>VideoFree 插件已经保存工作流、参数界面和模型规则；ComfyUI 端只需要具备该插件声明的模型与节点。不要再把网上来源不明的工作流混进 VideoFree 插件目录。</p>
            <p><strong>已经有 ComfyUI：</strong>把网盘里的模型放到你自己的 <code>ComfyUI/models/</code>，插件放到 <code>ComfyUI/custom_nodes/</code>。按包里的目录结构放，不要把所有文件都倒进一个文件夹，也不要随便改模型名。</p>
            <p><strong>还没有 ComfyUI：</strong>如果网盘提供完整安装包，下载并解压到空间充足的目录，按包内说明启动；如果只有模型和插件，先从 <a href="https://www.comfy.org/download" target="_blank" rel="noopener noreferrer">ComfyUI 官网</a>安装，再复制配套文件。</p>
            <pre>你的 ComfyUI/
├─ models/        ← 模型，保留各自子目录
└─ custom_nodes/  ← 插件，每个插件一个完整文件夹</pre>
          </section>
          <section class="step">
            <h2><b>2</b>更新 ComfyUI，装好插件依赖</h2>
            <p>先备份配置，再用你安装包自带的更新工具把 ComfyUI 更新到最新稳定版本。如果用了 Manager，也检查配套插件是否需要更新。不同安装包的更新按钮不一样，找不到就让智能体先检查安装方式。</p>
            <p>复制插件不等于安装完成，有些插件还需要安装依赖。让智能体在 <strong>ComfyUI 自己的 Python 环境</strong>里处理。更新后重启，看启动日志有没有“导入失败”或 “IMPORT FAILED”。</p>
          </section>
          <section class="step">
            <h2><b>3</b>让智能体安装 SageAttention</h2>
            <p>配套工作流需要 SageAttention。它不是模型，也不是复制一个节点文件夹就能装好的东西。把下面这段话发给能操作你电脑的智能体，最后填上你的 ComfyUI 路径：</p>
            <blockquote>{{ sagePrompt }}</blockquote>
            <p class="note">不建议照抄网上不明版本的安装命令。版本不匹配可能让原来能跑的 ComfyUI 也启动不了。</p>
          </section>
          <section class="step">
            <h2><b>4</b>启动 ComfyUI，记下它的地址</h2>
            <p>等启动完成，控制台会显示类似 <code>http://127.0.0.1:8189</code> 的地址。先在浏览器打开，能看到 ComfyUI 页面才算启动成功。端口以你自己的日志为准，也可能是 8188 或别的数字。</p>
            <p>不要关闭启动窗口，关了服务也就停了。以后使用 videofree 时，ComfyUI 也要保持运行。</p>
          </section>
          <section class="step">
            <h2><b>5</b>启动 videofree，填连接地址</h2>
            <p>Windows 解压完整 VideoFree 发布包后双击 <code>videofree.bat</code>；Linux 源码部署先安装 <code>requirements.txt</code>，再运行 <code>chmod +x videofree.sh &amp;&amp; ./videofree.sh</code>。打开首页，点右上角“进入工作台”，先创建并进入一个项目，再点左侧工具栏的齿轮设置按钮。</p>
            <p>使用剪辑插件还需自行安装 FFmpeg，并确保启动 VideoFree 的环境可以执行 <code>ffmpeg -version</code> 和 <code>ffprobe -version</code>。VideoFree 不随仓库分发这两个程序。</p>
            <p>在 <strong>ComfyUI / 网关地址</strong>填上刚才记下的 ComfyUI 地址，然后保存。两边在同一台电脑就用 <code>127.0.0.1</code>；不在同一台电脑，要填 ComfyUI 那台电脑的局域网 IP。</p>
            <figure><a href="/contact/guide-settings.png" target="_blank" rel="noopener noreferrer"><img :src="'/contact/guide-settings.png'" alt="工作台设置窗口，ComfyUI 接口地址位于顶部" loading="lazy" /></a><figcaption>设置界面示例：顶部填写 ComfyUI 地址，底部保存。点击图片查看大图。</figcaption></figure>
            <p class="note">ComfyUI 地址和 videofree 地址不是一回事。8189 是这里的 ComfyUI 示例端口，8765 是 videofree 默认端口；不要把 8765 填进 ComfyUI 接口地址。</p>
          </section>
          <section class="step">
            <h2><b>6</b>补齐 AI 配置，创建项目试一下</h2>
            <p>需要 H3 描述词转换或导演协作，就在设置里填 AI 服务地址、模型名和 API Key。需要 GPT-Image 云端生图，再填 GrisAI API Key；只用本地生图，不需要这个云端密钥。</p>
            <p>回到项目列表，创建项目，再进项目生成。先用低分辨率、短视频或一张图片试跑，确认连接和依赖正常，再做长视频。素材会自动存到 <code>data/projects/</code> 对应项目，不用手动同步 ComfyUI 的输出目录。</p>
            <figure><a href="/contact/guide-projects.png" target="_blank" rel="noopener noreferrer"><img :src="'/contact/guide-projects.png'" alt="工作台项目列表和创建项目入口" loading="lazy" /></a><figcaption>空项目列表示例：先创建项目，再进入项目生成。</figcaption></figure>
          </section>
          <section class="step troubleshooting">
            <h2>遇到问题，先看这几项</h2>
            <p><strong>缺节点：</strong>对应插件没装好，或依赖导入失败。检查 ComfyUI 启动日志，修好后重启。</p>
            <p><strong>缺模型：</strong>检查文件名和子目录，不能只看“下载过了”。</p>
            <p><strong>网关在线但不能生成：</strong>只说明 videofree 在运行，不代表 ComfyUI 已连上。</p>
            <p><strong>显存不足：</strong>先减分辨率和时长。不是所有模型、尺寸都能在任意显卡运行。</p>
            <p><strong>局域网打不开：</strong>用电脑的实际 IP，不要用 <code>0.0.0.0</code>。跨电脑连接还要检查监听地址和 Windows 防火墙，别把免认证服务暴露到公网。</p>
          </section>
          <button class="next-button" type="button" @click="$emit('section', 'mcp')">下一步：安装 MCP <Icon icon="solar:arrow-right-linear" width="18" /></button>
        </template>
        <template v-else-if="section === 'mcp'">
          <div class="eyebrow">板块二 / 连接智能体</div>
          <h1>MCP 安装</h1>
          <p class="intro">MCP 是让支持 MCP 的 AI 直接调用 videofree 生成、查询和管理项目的连接方式。它随网关一起启动，不需要另外运行 MCP 服务。</p>
          <section class="step">
            <h2><b>1</b>确认网关地址</h2>
            <p>先启动 videofree。默认端口是 <code>8765</code>，MCP 地址固定为 <code>/mcp</code>。</p>
            <p><strong>同一台电脑：</strong>使用 <code>http://127.0.0.1:8765/mcp</code>。</p>
            <p><strong>局域网其他电脑：</strong>把 <code>127.0.0.1</code> 换成运行网关电脑的实际局域网 IP，例如 <code>http://192.168.50.8:8765/mcp</code>。不要填写 <code>0.0.0.0</code>，也不要把地址改成 <code>/sse</code>。</p>
          </section>
          <section class="step">
            <h2><b>2</b>粘贴客户端配置</h2>
            <p>在 AI 客户端的 MCP 服务配置中新增一个服务，名称填 <code>videofree</code>，然后粘贴下面的 JSON。不同客户端可能要求把 <code>type</code> 改成 <code>streamable-http</code>，以客户端文档为准。</p>
            <pre>{
  "mcpServers": {
    "videofree": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}</pre>
            <p>从另一台电脑连接时，只需要把 JSON 中的地址替换成网关电脑 IP：</p>
            <pre>{
  "mcpServers": {
    "videofree": {
      "type": "http",
      "url": "http://192.168.50.8:8765/mcp"
    }
  }
}</pre>
          </section>
          <section class="step">
            <h2><b>3</b>需要令牌时加入认证</h2>
            <p>默认令牌为空，不需要认证请求头。如果你在工作台设置中配置了网关访问令牌，在服务配置中加入 <code>headers</code>，并把示例值替换为真实令牌：</p>
            <pre>{
  "mcpServers": {
    "videofree": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "X-API-Token": "你的令牌"
      }
    }
  }
}</pre>
            <p class="note">不要把令牌写进公开提示词、截图或代码仓库。HTTP API 和 MCP 共用工作台中的同一个令牌。</p>
          </section>
          <section class="step">
            <h2><b>4</b>刷新工具并验证连接</h2>
            <p>保存配置后刷新 AI 客户端的 MCP 工具列表。先让 AI 调用 <code>get_health</code>、<code>list_capabilities</code> 和 <code>list_voices</code>，能正常返回结果才表示连接完成。</p>
            <p>客户端必须支持 HTTP POST 的 JSON 响应。旧版只支持 SSE 的客户端不能直接使用这个地址；不要把 MCP 地址改成 <code>/sse</code>。</p>
            <p>如果局域网连接失败，检查网关监听地址、防火墙和令牌是否一致。网关在线不代表 ComfyUI 已连接，生成失败时再检查工作台里的 ComfyUI 地址。</p>
          </section>
          <button class="next-button" type="button" @click="$emit('section', 'skills')">下一步：安装全自动技能包 <Icon icon="solar:arrow-right-linear" width="18" /></button>
        </template>
        <template v-else-if="section === 'skills'">
          <div class="eyebrow">板块三 / 交给智能体制作</div>
          <h1>全自动技能包安装使用</h1>
          <p class="intro">技能包是给智能体看的制作说明和工具，不是双击就能出片的软件。先完成安装部署，再接上你常用的智能体。</p>
          <section class="step">
            <h2><b>1</b>准备两个完整技能文件夹</h2>
            <p>在 videofree 项目的 <code>.agents/skills/</code> 里找到下面两个目录，一起复制到你的智能体支持的技能目录。一定复制整个文件夹，不要只复制 <code>SKILL.md</code>。</p>
            <pre>智能体的技能目录/
├─ dialogue-video-skill/  ← 负责策划、分镜、生成与审核
└─ openmontage/          ← 负责剪辑、混音和最终合成</pre>
            <p>媒体生成由主制片直接调用 videofree 的 MCP，按下面第 3 步配置即可，不需要再安装其他媒体调用技能。</p>
            <p>不同智能体的安装位置不一样，可以直接问它“你的技能安装目录在哪”。原来的 <code>dialogue-man</code> 不用搬，新技能不依赖它。OpenMontage 的完整源码、AGPL-3.0 许可证和版权声明都要保留。</p>
          </section>
          <section class="step">
            <h2><b>2</b>让智能体检查环境和依赖</h2>
            <p>生成在 videofree 这边进行，剪辑合成在智能体的运行环境进行。所以智能体那边也需要 Python 3.10+、FFmpeg 和 ffprobe，以及 OpenMontage 的 Python 依赖。下面这段可以直接发给它：</p>
            <blockquote>{{ installPrompt }}</blockquote>
            <p>选择 Remotion 或 HyperFrames 时，才需要额外安装对应 Node 依赖。普通 FFmpeg 合成不必先装所有渲染工具。</p>
          </section>
          <section class="step">
            <h2><b>3</b>连接 videofree 的 MCP</h2>
            <p>在智能体的 MCP 配置里添加一个 HTTP 服务，名字可填 <code>videofree</code>，地址填 <code>http://你的网关电脑IP:8765/mcp</code>。它随 videofree 一起启动，不用再单独开一个服务。</p>
            <p>同机可以用 <code>http://127.0.0.1:8765/mcp</code>。另一台电脑必须用真实局域网 IP，例如 <code>http://192.168.50.8:8765/mcp</code>，不要照抄成自己的地址。</p>
            <p>让智能体先检查健康状态、查询可用能力和预设音色。能查到才说明连接成功。各平台配置格式不同，参照当前智能体的 HTTP MCP 配置说明和 <code>dialogue-video-skill/references/install.md</code>，不要把某个平台的 JSON 当成通用格式。</p>
            <p class="note">这套全自动视频技能使用 MCP。请选用支持 HTTP MCP 的智能体，只给主制片配置媒体服务。</p>
          </section>
          <section class="step">
            <h2><b>4</b>刷新技能，让它检查能不能用</h2>
            <p>刷新或重启智能体，让它读到新技能。让它检查固定人物资产、工具链和下载权限，再跑 OpenMontage 的 preflight 检查。没有图像、视频或声音审核能力，就必须说明限制，不能假装已经审核通过。</p>
            <p>支持子智能体时，只有主制片连接媒体生成工具；剧本、分镜和 QA 按任务给权限，别让每个子智能体都随意提交生成。权限隔离要在宿主设置，技能文字本身不能代替权限配置。</p>
          </section>
          <section class="step">
            <h2><b>5</b>先做一个短片，再开全自动</h2>
            <p>第一次先发这个例子，确认人物、声音、生成和合成都正常：</p>
            <blockquote>{{ example }}</blockquote>
            <p>跑通后再授权全自动。把主题、时长、画幅、生成次数或费用上限、是否二采、哪些环节需要你确认说清楚。出现参考图身份不明确等问题，智能体仍应停下来问你，不能盲目确认。</p>
            <p>例如：“方案确认，最多提交 12 次生成，允许二采；无歧义的步骤自动继续，有身份或预算问题先问我。”</p>
          </section>
          <section class="step">
            <h2><b>6</b>找到结果，保留制作记录</h2>
            <p>生成素材保存在 videofree 的项目里。让智能体先创建专属项目，后续提交带项目 ID，避免和你手动生成的素材混在一起。</p>
            <p>最终剪辑成片保存在智能体约定的交付目录，不一定在 videofree 项目目录。开始前让它告诉你输出到哪里。每次制作使用独立工作目录，保留方案、素材清单和审核记录，不要往技能文件夹里堆成片。</p>
          </section>
          <button class="next-button" type="button" @click="$emit('enter')">进入工作台 <Icon icon="solar:arrow-right-linear" width="18" /></button>
        </template>
        <template v-else>
          <div class="eyebrow">板块四 / 扩展自己的能力</div>
          <h1>开发 VideoFree 插件</h1>
          <p class="intro">把已经调通的 ComfyUI 工作流、模型规则、参数界面和固定资源放进一个插件目录，让工作台用户和外部 Agent 使用同一套稳定能力。</p>
          <section class="step">
            <h2><b>1</b>选择插件形态</h2>
            <p><strong>生成插件</strong>封装图片、视频、语音或音乐工作流；<strong>动作插件</strong>提供二采、增强或业务操作；<strong>项目小插件</strong>在当前项目或分类中管理剧本、进度等数据；<strong>应用插件</strong>拥有完整独立页面，例如剪辑工具。</p>
          </section>
          <section class="step">
            <h2><b>2</b>把全部专用内容留在插件内部</h2>
            <p>插件的 <code>plugin.json</code> 是唯一注册入口。工作流、编译器、协作技能、Vue 页面、图标、预设和固定样本都必须随插件分发；不能把模型专用规则写进框架，也不能直接读取平台数据库或其他插件代码。</p>
          </section>
          <section class="step">
            <h2><b>3</b>让开发智能体读取专用 Skill</h2>
            <p>仓库已经提供 <code>.agents/skills/videofree-plugin-development/</code>。把完整目录安装到开发智能体的技能目录，然后发送：</p>
            <blockquote>使用 $videofree-plugin-development，把我的 ComfyUI 工作流制作成 VideoFree 插件。先分析输入、输出、模型依赖和插件形态，再实现、测试并运行发布自检；所有模型专用代码和资源必须留在插件目录。</blockquote>
          </section>
          <section class="step">
            <h2><b>4</b>按真实协议开发和验证</h2>
            <p>详细字段、运行时接口和 UI 规则以仓库中的 <code>plugins/PLUGIN_DEVELOPMENT.md</code>、<code>docs/plugin-protocol.md</code>、<code>ARCHITECTURE.md</code> 为准。完成后至少验证插件扫描、相关测试、前端构建（有 UI 时）和 <code>videofree.bat --check</code>（Linux 使用 <code>./videofree.sh --check</code>）。</p>
            <p class="note">插件是可信本地代码，不是安全沙箱。安装或更新前先排空相关任务，更新后重启网关；插件不会自动替用户安装 ComfyUI 模型和节点。</p>
          </section>
          <button class="next-button" type="button" @click="$emit('enter')">进入工作台 <Icon icon="solar:arrow-right-linear" width="18" /></button>
        </template>
      </main>
    </div>
    <PluginDialog :open="contactOpen" :framed="false" title="微信咨询 · 有偿安装" @close="contactOpen = false"><section class="contact-dialog">
      <header>
        <h2 id="contact-dialog-title">微信咨询 · 有偿安装</h2>
        <button class="contact-close" type="button" aria-label="关闭微信二维码" title="关闭" @click="contactOpen = false"><Icon icon="solar:close-circle-linear" width="24" /></button>
      </header>
      <img src="/contact/weixin.png" alt="AI老林微信咨询二维码" />
    </section></PluginDialog>
  </div>
</template>

<style scoped>
.guide-page { height: 100%; overflow: auto; background: #151816; color: #f0f3ef; font-family: "Microsoft YaHei", sans-serif; letter-spacing: 0; }
.guide-page * { box-sizing: border-box; }
.guide-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 40px; border-bottom: 1px solid #303330; }
button { font: inherit; cursor: pointer; }
.home-link { display: inline-flex; align-items: center; gap: 10px; border: 0; padding: 0; background: transparent; color: #f0f3ef; font-size: 15px; }
.enter-button, .next-button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; border: 0; border-radius: 5px; padding: 11px 16px; background: #b5e7c9; color: #18291f; font-size: 14px; }
.guide-layout { display: grid; grid-template-columns: 210px minmax(0, 850px); justify-content: center; align-items: start; gap: 60px; padding: 42px 40px 64px; }
.guide-nav { position: sticky; top: 24px; display: grid; gap: 12px; }
.guide-nav > span { font-size: 12px; color: #89988d; margin-bottom: 8px; }
.guide-nav button { border: 0; border-left: 2px solid transparent; padding: 10px 12px; text-align: left; background: transparent; color: #a3aaa5; font-size: 14px; }
.guide-nav button.active { border-color: #9be0bb; color: #9be0bb; background: #202b23; }
.guide-nav a { display: flex; align-items: center; gap: 8px; margin-top: 14px; font-size: 13px; }
.guide-nav small { color: #a3aaa5; }
.guide-content { min-width: 0; }
.installation-help { display: flex; align-items: center; gap: 12px; width: 100%; margin-bottom: 28px; padding: 16px 18px; border: 1px solid #6f6049; border-radius: 5px; background: #29271f; color: #e7bf85; text-align: left; }
.installation-help > svg { flex-shrink: 0; }
.installation-help > span { flex: 1; min-width: 0; }
.installation-help strong { display: block; color: #e7bf85; font-size: 15px; line-height: 1.7; }
.installation-help small { display: block; margin-top: 3px; color: #b6beb8; font-size: 12px; line-height: 1.7; }
.installation-help:hover { border-color: #e7bf85; }
.contact-dialog { box-sizing:border-box; width: min(420px, calc(100vw - 32px)); max-height: calc(100dvh - 32px); margin: auto; padding: 16px; border: 1px solid #303330; border-radius: 8px; background: #202420; color: #f0f3ef; }
.contact-dialog header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.contact-dialog h2 { margin: 0; font-size: 17px; }
.contact-close { display: grid; place-items: center; flex-shrink: 0; width: 32px; height: 32px; padding: 0; border: 0; background: transparent; color: inherit; }
.contact-dialog img { display: block; width: 100%; max-height: calc(100dvh - 120px); object-fit: contain; }
.eyebrow { color: #9be0bb; font-size: 12px; }
h1 { margin: 12px 0 16px; font-size: 32px; line-height: 1.5; }
.intro { margin-bottom: 30px; color: #a3aaa5; font-size: 15px; line-height: 1.9; }
.step { border-top: 1px solid #303330; padding: 26px 0; }
h2 { display: flex; align-items: baseline; gap: 12px; margin: 0 0 18px; font-size: 20px; line-height: 1.6; }
h2 b { color: #9be0bb; font-size: 16px; }
p { margin: 12px 0; color: #b6beb8; font-size: 14px; line-height: 1.95; }
strong { color: #f0f3ef; }
a { color: #9be0bb; text-underline-offset: 4px; }
code { color: #e7bf85; font-size: 13px; overflow-wrap: anywhere; }
pre { padding: 18px; background: #202420; border-radius: 5px; overflow: auto; color: #ccd6ce; font-size: 13px; line-height: 1.9; }
blockquote { margin: 16px 0; padding: 16px 20px; border-left: 3px solid #9be0bb; background: #202420; font-size: 14px; line-height: 1.95; overflow-wrap: anywhere; user-select: text; }
.note { padding-left: 14px; border-left: 2px solid #e7bf85; color: #e7bf85; font-size: 13px; }
figure { margin: 22px 0; }
figure img { display: block; width: 100%; height: auto; border: 1px solid #303330; border-radius: 5px; }
figcaption { margin-top: 8px; font-size: 12px; color: #89988d; line-height: 1.7; }
a:focus-visible, button:focus-visible { outline: 2px solid #9be0bb; outline-offset: 4px; }
@media (max-width: 800px) {
  .guide-header { padding: 16px 20px; }
  .guide-layout { grid-template-columns: minmax(0, 1fr); gap: 28px; padding: 24px 20px 40px; }
  .guide-nav { position: static; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .guide-nav > span, .guide-nav a, .guide-nav small { display: none; }
  .guide-nav button { padding: 10px 6px; font-size: 13px; }
  h1 { font-size: 26px; }
  h2 { font-size: 18px; }
  .home-link { font-size: 13px; }
  .enter-button { font-size: 12px; padding: 10px; }
  blockquote { padding: 14px; }
}
</style>
