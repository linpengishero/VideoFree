<script setup>
import { Icon } from "@iconify/vue";
import { ref } from "vue";
import PluginDialog from './PluginDialog.vue';

defineEmits(["enter", "guide"]);

const qrOpen = ref(false);
const activeQr = ref({ src: "", title: "" });

function openQr(src, title) {
  activeQr.value = { src, title };
  qrOpen.value = true;
}

function closeQr() {
  qrOpen.value = false;
}

const capabilities = [
  { icon: "solar:widget-5-linear", title: "工作流插件化", description: "把模型、工作流、参数和资源封装成可安装能力。" },
  { icon: "solar:magic-stick-3-linear", title: "大白话创作", description: "按模型规则追问和整理提示词，降低学习门槛。" },
  { icon: "solar:folder-with-files-linear", title: "项目化管理", description: "统一管理剧本、分类、任务、素材与项目资产。" },
  { icon: "solar:link-linear", title: "Agent 稳定调用", description: "通过 MCP/API 发现和调用能力，不接触节点连线。" },
];

const services = [
  { icon: "solar:server-square-cloud-linear", title: "企业级大模型部署", description: "私有化部署、知识库与 RAG、推理服务。" },
  { icon: "solar:stars-minimalistic-linear", title: "企业 AI 自动化", description: "连接业务系统，让 AI 参与实际生产流程。" },
  { icon: "solar:diagram-up-linear", title: "智能体与工作流定制", description: "多智能体协作、媒体工作流与持续维护。" },
];
</script>

<template>
  <div class="landing-page">
    <header class="landing-nav">
      <a class="landing-brand" href="/" aria-label="videofree 首页">
        <img src="/contact/logo.png" alt="" width="32" height="32" />
        <strong>videofree</strong>
      </a>
      <button class="studio-button" type="button" @click="$emit('enter')">
        进入工作台 <Icon icon="solar:arrow-right-linear" width="18" />
      </button>
    </header>

    <main class="landing-main">
      <div class="product-column">
        <section class="product-intro" aria-labelledby="landing-title">
          <div class="section-label"><span class="label-mark"></span> 本地 AI 视频创作平台</div>
          <h1 id="landing-title">videofree</h1>
          <p class="product-subtitle">让复杂的本地工作流，成为真正可用的创作能力。</p>
          <p class="product-description">以 ComfyUI 为生成引擎，把零散模型、复杂节点、提示词规则和配套资源封装成插件。普通用户可以用大白话创作，开发者可以分发能力，Agent 可以通过稳定接口自动调用。</p>
          <div class="product-modes" aria-label="支持的创作方式">
            <span><Icon icon="solar:monitor-linear" width="15" /> 本地模型</span>
            <span><Icon icon="solar:cloud-linear" width="15" /> 云端生成</span>
            <span><Icon icon="solar:link-linear" width="15" /> 智能体协作</span>
          </div>
        </section>

        <section class="product-features" aria-label="videofree 产品能力">
          <article v-for="item in capabilities" :key="item.title" class="feature-item">
            <Icon :icon="item.icon" width="22" />
            <div><h2>{{ item.title }}</h2><p>{{ item.description }}</p></div>
          </article>
        </section>

        <section class="resource-section community-section" aria-labelledby="community-title">
          <div class="resource-copy">
            <span class="section-label">学习与实践 · 知识星球</span>
            <h2 id="community-title">把 AI 创作变成可复用的流水线</h2>
            <p>分享各类 AI 视频自动化流水线、智能体实践与大模型专业知识。从实际案例出发，持续更新可落地的方法与经验。</p>
            <span class="resource-note">AI 视频自动化 / 智能体 / 大模型</span>
            <div class="guide-links">
              <button type="button" @click="$emit('guide', 'install')"><Icon icon="solar:monitor-linear" width="16" />安装部署教程</button>
              <button type="button" @click="$emit('guide', 'mcp')"><Icon icon="solar:plug-circle-linear" width="16" />MCP 安装教程</button>
              <button type="button" @click="$emit('guide', 'skills')"><Icon icon="solar:book-linear" width="16" />全自动技能包教程</button>
              <button type="button" @click="$emit('guide', 'plugin')"><Icon icon="solar:widget-add-linear" width="16" />插件开发教程</button>
            </div>
          </div>
          <div class="community-qr-list">
            <button class="qr-link" type="button" @click="openQr('/contact/zsxq-qr.png', '知识星球')" aria-label="放大知识星球二维码">
              <img src="/contact/zsxq-qr.png" alt="知识星球二维码" width="200" height="200" loading="lazy" />
              <span>知识星球</span>
            </button>
            <button class="qr-link" type="button" @click="openQr('https://laobanclaw.top/videofree/qrcode.jpg', 'VideoFree 微信交流群')" aria-label="放大 VideoFree 微信交流群二维码">
              <img src="https://laobanclaw.top/videofree/qrcode.jpg" alt="VideoFree 微信交流群二维码" width="200" height="200" loading="lazy" referrerpolicy="no-referrer" />
              <span>微信交流群</span>
            </button>
          </div>
        </section>

      </div>

      <aside class="business-column" aria-labelledby="contact-title">
        <section class="business-intro">
          <span class="section-label">AI老林 · 技术服务与合作</span>
          <h2 id="contact-title">让 AI 进入业务，<br />交付真正可运行的系统。</h2>
          <p>面向企业与团队，提供从需求梳理、方案设计到部署交付的技术服务，让 AI 能落地，也能长期维护。</p>
        </section>

        <div class="service-list" aria-label="个人技术服务">
          <article v-for="service in services" :key="service.title">
            <Icon :icon="service.icon" width="21" />
            <div><h3>{{ service.title }}</h3><p>{{ service.description }}</p></div>
          </article>
        </div>

        <div class="business-contact">
          <section class="contact-item" aria-labelledby="wechat-title">
            <h3 id="wechat-title">微信咨询与合作</h3>
            <p>扫码聊需求</p>
            <button class="qr-link" type="button" @click="openQr('/contact/weixin.png', '微信咨询与合作')" aria-label="放大微信咨询二维码">
              <img src="/contact/weixin.png" alt="AI老林微信咨询二维码" width="120" height="120" loading="lazy" />
            </button>
          </section>
          <section class="contact-item" aria-labelledby="support-title">
            <h3 id="support-title">支持 videofree</h3>
            <p>您的支持，是我前进的动力</p>
            <button class="qr-link support-qr" type="button" @click="openQr('/contact/wechat-support.jpg', '支持 videofree')" aria-label="放大微信收款码">
              <img src="/contact/wechat-support.jpg" alt="微信自愿支持收款码" width="745" height="1014" loading="lazy" />
            </button>
          </section>
        </div>

        <a class="arsenal-link" href="https://laobanclaw.top/" target="_blank" rel="noopener noreferrer">
          <div>
            <span class="section-label">AI军火库</span>
            <strong>laobanclaw.top</strong>
            <p>前沿 AI 技术、工具与实践</p>
          </div>
          <Icon icon="solar:arrow-right-up-linear" width="25" />
        </a>
      </aside>
    </main>

    <footer class="landing-footer">
      <span>© 2026 AI老林 · videofree</span>
      <span>让创作更自由，让技术真正落地。</span>
    </footer>
    <PluginDialog :open="qrOpen" :framed="false" :title="activeQr.title" @close="closeQr"><section class="qr-dialog">
      <header>
        <h2 id="qr-dialog-title">{{ activeQr.title }}</h2>
        <button type="button" class="qr-close" aria-label="关闭二维码" title="关闭" @click="closeQr"><Icon icon="solar:close-circle-linear" width="24" /></button>
      </header>
      <img v-if="activeQr.src" :src="activeQr.src" :alt="activeQr.title" />
    </section></PluginDialog>
  </div>
</template>

<style scoped>
.landing-page {
  --page-gutter: 40px;
  --line: #303330;
  --muted: #a3aaa5;
  --green: #9be0bb;
  height: 100%;
  overflow: auto;
  background: #151816;
  color: #f0f3ef;
  font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  letter-spacing: 0;
}
.landing-page *, .landing-page *::before, .landing-page *::after { box-sizing: border-box; }
.landing-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 76px;
  padding: 16px var(--page-gutter);
  border-bottom: 1px solid var(--line);
}
.landing-brand { display: inline-flex; align-items: center; gap: 10px; color: inherit; text-decoration: none; }
.landing-brand img { object-fit: contain; }
.landing-brand strong { font-size: 18px; }
.studio-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 40px;
  padding: 0 18px;
  border: 1px solid #b5e7c9;
  border-radius: 5px;
  background: #b5e7c9;
  color: #18291f;
  font-size: 14px;
  font-weight: 650;
  cursor: pointer;
}
.studio-button:hover { background: #cdf3db; border-color: #cdf3db; }
.landing-main {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(340px, 1fr);
  gap: 48px;
  margin: 0 var(--page-gutter);
  padding: 48px 0 40px;
}
.product-column, .business-column { min-width: 0; }
.section-label { display: inline-flex; align-items: center; gap: 8px; color: var(--green); font-size: 12px; font-weight: 600; line-height: 1.6; }
.label-mark { width: 6px; height: 6px; background: var(--green); }
.product-intro h1 { margin: 16px 0 14px; font-size: 64px; font-weight: 650; line-height: 1.05; letter-spacing: 0; }
.product-subtitle { margin: 0 0 14px; font-size: 23px; font-weight: 500; line-height: 1.5; }
.product-description { max-width: 680px; margin: 0; color: var(--muted); font-size: 14px; line-height: 1.85; }
.product-modes { display: flex; flex-wrap: wrap; gap: 12px 24px; margin-top: 22px; }
.product-modes span { display: inline-flex; align-items: center; gap: 7px; color: #c1c9c3; font-size: 12px; }
.product-modes svg { color: var(--green); }
.product-features { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px 30px; padding: 28px 0; margin-top: 28px; border-top: 1px solid var(--line); }
.feature-item { display: grid; grid-template-columns: 24px minmax(0, 1fr); gap: 12px; align-items: start; }
.feature-item > svg { color: var(--green); }
.feature-item h2 { margin: 0 0 7px; font-size: 15px; font-weight: 600; }
.feature-item p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.7; }
.resource-section { display: grid; grid-template-columns: minmax(0, 1fr) 120px; align-items: center; gap: 28px; padding: 26px 0; border-top: 1px solid var(--line); }
.community-section { grid-template-columns: minmax(0, 1fr) auto; }
.community-qr-list { display: flex; align-items: flex-start; gap: 16px; }
.resource-copy { min-width: 0; }
.resource-copy h2 { margin: 9px 0 10px; font-size: 19px; font-weight: 600; line-height: 1.5; }
.resource-copy p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.8; }
.resource-note { display: block; margin-top: 14px; color: #76867b; font-size: 12px; line-height: 1.7; }
.guide-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
.guide-links button { display: inline-flex; align-items: center; gap: 6px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 5px; background: transparent; color: var(--green); font: inherit; font-size: 12px; cursor: pointer; }
.guide-links button:hover { border-color: var(--green); }
.qr-link { display: grid; gap: 8px; width: 120px; padding: 0; border: 0; background: transparent; color: var(--muted); font: inherit; text-align: center; cursor: pointer; }
.qr-dialog { box-sizing:border-box; width: min(440px, calc(100vw - 32px)); max-height: calc(100dvh - 32px); margin: auto; padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: #202420; color: #f0f3ef; }
.qr-dialog header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.qr-dialog h2 { margin: 0; font-size: 17px; }
.qr-close { display: grid; place-items: center; flex-shrink: 0; width: 32px; height: 32px; padding: 0; border: 0; background: transparent; color: inherit; cursor: pointer; }
.qr-dialog > img { display: block; width: 100%; max-height: calc(100dvh - 120px); object-fit: contain; }
.qr-link img { display: block; width: 100%; height: auto; aspect-ratio: 1; object-fit: contain; background: #fff; border-radius: 3px; }
.qr-link span { font-size: 11px; line-height: 1.6; }
.support-qr img { aspect-ratio: 745 / 1014; }
.business-column { padding-left: 36px; border-left: 1px solid var(--line); }
.business-intro .section-label { color: #e7bf85; }
.business-intro h2 { margin: 16px 0 18px; font-size: 27px; font-weight: 600; line-height: 1.55; }
.business-intro > p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.85; }
.service-list { margin-top: 26px; border-top: 1px solid var(--line); }
.service-list article { display: grid; grid-template-columns: 23px minmax(0, 1fr); gap: 12px; padding: 20px 0; border-bottom: 1px solid var(--line); }
.service-list article > svg { color: #e7bf85; }
.service-list h3 { margin: 0 0 7px; font-size: 15px; font-weight: 600; }
.service-list p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.8; }
.business-contact { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: start; padding: 24px 0; }
.contact-item { min-width: 0; }
.business-contact h3 { margin: 0 0 6px; font-size: 15px; font-weight: 600; line-height: 1.6; }
.business-contact p { min-height: 36px; margin: 0 0 12px; color: var(--muted); font-size: 12px; line-height: 1.5; }
.business-contact .qr-link { width: min(120px, 100%); }
.business-contact .qr-link img { height: auto; aspect-ratio: 1; object-fit: cover; }
.arsenal-link { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); color: var(--green); text-decoration: none; }
.arsenal-link > div { min-width: 0; }
.arsenal-link strong { display: inline-block; margin: 0 0 0 12px; color: #ecf3ee; font-size: 18px; font-weight: 600; line-height: 1.5; overflow-wrap: anywhere; }
.arsenal-link p { margin: 4px 0 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
.arsenal-link > svg { flex-shrink: 0; }
.arsenal-link:hover strong, .qr-link:hover span { color: var(--green); }
.landing-page a:focus-visible, .landing-page button:focus-visible { outline: 2px solid var(--green); outline-offset: 5px; }
.landing-footer { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px; padding: 22px var(--page-gutter); border-top: 1px solid var(--line); color: #88958c; font-size: 12px; line-height: 1.7; }
@media (min-width: 1600px) {
  .landing-main { grid-template-columns: minmax(0, 1.7fr) minmax(400px, 1fr); gap: 64px; }
  .product-features { gap: 26px 40px; }
  .resource-section { grid-template-columns: minmax(0, 1fr) 140px; }
  .resource-section .qr-link { width: 140px; }
}
@media (max-width: 1050px) {
  .landing-page { --page-gutter: 28px; }
  .landing-main { gap: 28px; grid-template-columns: minmax(0, 1.4fr) minmax(300px, 1fr); }
  .business-column { padding-left: 24px; }
  .business-intro h2 { font-size: 23px; }
  .resource-section { gap: 20px; grid-template-columns: minmax(0, 1fr) 104px; }
  .resource-section .qr-link { width: 104px; }
  .product-subtitle { font-size: 20px; }
}
@media (max-width: 800px) {
  .landing-main { grid-template-columns: 1fr; gap: 32px; padding: 32px 0; }
  .business-column { border-left: 0; padding: 32px 0 0; border-top: 1px solid var(--line); }
  .business-intro h2 { font-size: 27px; }
  .resource-section { grid-template-columns: minmax(0, 1fr) 120px; }
  .resource-section .qr-link { width: 120px; }
}
@media (max-width: 480px) {
  .landing-page { --page-gutter: 20px; }
  .landing-nav { min-height: 68px; }
  .landing-brand strong { font-size: 16px; }
  .studio-button { padding: 0 12px; font-size: 13px; }
  .product-intro h1 { font-size: 48px; }
  .product-subtitle { font-size: 19px; }
  .product-features { gap: 24px 18px; }
  .feature-item { grid-template-columns: 1fr; gap: 10px; }
  .resource-section { gap: 18px; grid-template-columns: minmax(0, 1fr) 104px; }
  .resource-section .qr-link { width: 104px; }
  .community-section { grid-template-columns: 1fr; }
  .community-qr-list { gap: 14px; }
  .resource-copy h2 { font-size: 17px; }
  .resource-note { display: none; }
  .business-intro h2 { font-size: 24px; }
  .arsenal-link strong { font-size: 17px; }
  .landing-footer { flex-direction: column; }
}
@media (max-width: 360px) {
  .landing-page { --page-gutter: 16px; }
  .resource-section { grid-template-columns: 1fr; }
  .resource-section .qr-link { width: 120px; }
}
@media (min-width: 1051px) {
  .community-section .community-qr-list .qr-link { width: 200px; }
}
@media (min-width: 801px) and (max-width: 1050px) {
  .community-section .community-qr-list .qr-link { width: 150px; }
}
@media (min-width: 481px) and (max-width: 800px) {
  .community-section .community-qr-list .qr-link { width: 160px; }
}
@media (max-width: 480px) {
  .community-section .community-qr-list .qr-link { width: 112px; }
}
</style>
