<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { Icon } from "@iconify/vue";
import packageInfo from "../../package.json";
import { t } from "../services/i18n";

defineEmits(["enter"]);

const announcementFailed = ref(false);
const backgroundCanvas = ref(null);
const version = packageInfo.version;
let animationFrame = 0;
let resizeObserver;
let stopAnimation = false;

function startBackground() {
  const canvas = backgroundCanvas.value;
  const context = canvas?.getContext("2d", { alpha: true });
  if (!canvas || !context) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const nodes = Array.from({ length: 78 }, () => ({
    x: Math.random(), y: Math.random(),
    vx: (Math.random() - 0.5) * 0.012,
    vy: (Math.random() - 0.5) * 0.009,
    phase: Math.random() * Math.PI * 2,
  }));
  let width = 0;
  let height = 0;
  let lastFrame = 0;
  let gridOffset = 0;

  const resize = () => {
    const bounds = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    width = bounds.width;
    height = bounds.height;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    cancelAnimationFrame(animationFrame);
    lastFrame = 0;
    if (reducedMotion) {
      draw(performance.now(), true);
    } else {
      animationFrame = requestAnimationFrame(draw);
    }
  };

  const draw = (timestamp, staticFrame = false) => {
    if (stopAnimation || (!staticFrame && timestamp - lastFrame < 40)) {
      if (!stopAnimation && !reducedMotion) animationFrame = requestAnimationFrame(draw);
      return;
    }
    const delta = Math.min(timestamp - lastFrame || 16, 50);
    const seconds = timestamp / 1000;
    lastFrame = timestamp;
    context.clearRect(0, 0, width, height);

    // A perspective grid anchors the scene like a live technical workspace.
    const horizon = height * 0.47;
    context.lineWidth = 1;
    for (let row = 0; row < 15; row += 1) {
      const progress = row / 14;
      const y = horizon + Math.pow((progress + gridOffset * 0.045) % 1, 1.7) * height * 0.62;
      context.strokeStyle = `rgba(72, 194, 207, ${0.075 + progress * 0.085})`;
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }
    if (!reducedMotion) gridOffset = (gridOffset + delta * 0.012) % 1;
    for (let ray = -13; ray <= 13; ray += 1) {
      const bottomX = width / 2 + ray * width / 13;
      context.strokeStyle = ray % 3 === 0 ? "rgba(87, 215, 206, 0.15)" : "rgba(87, 215, 206, 0.07)";
      context.beginPath();
      context.moveTo(width / 2 + ray * 2, horizon);
      context.lineTo(bottomX, height * 1.12);
      context.stroke();
    }

    // Slowly rotating instrument rings sit behind the product mark.
    const centerX = width / 2;
    const centerY = height * 0.24;
    context.save();
    context.translate(centerX, centerY);
    context.rotate(seconds * 0.035);
    [112, 146].forEach((radius, index) => {
      context.beginPath();
      context.setLineDash(index ? [2, 10] : [28, 12, 3, 12]);
      context.lineDashOffset = -seconds * (index ? 8 : 14);
      context.strokeStyle = index ? "rgba(73, 195, 211, 0.34)" : "rgba(121, 225, 177, 0.4)";
      context.lineWidth = index ? 1 : 1.4;
      context.arc(0, 0, radius, 0, Math.PI * 2);
      context.stroke();
    });
    context.setLineDash([]);
    context.beginPath();
    context.arc(0, 0, 166, seconds * 0.18, seconds * 0.18 + Math.PI * 0.28);
    context.strokeStyle = "rgba(243, 184, 102, 0.5)";
    context.lineWidth = 2;
    context.stroke();
    context.restore();

    // A bright scan traverses the field to make motion legible at a glance.
    const scanY = ((seconds * 0.075) % 1.2 - 0.1) * height;
    context.strokeStyle = "rgba(93, 218, 210, 0.34)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(0, scanY);
    context.lineTo(width, scanY);
    context.stroke();
    context.fillStyle = "rgba(93, 218, 210, 0.055)";
    context.fillRect(0, scanY - 18, width, 36);

    for (let i = 0; i < nodes.length; i += 1) {
      const point = nodes[i];
      if (!reducedMotion) {
        point.x = (point.x + point.vx * delta / 1000 + 1) % 1;
        point.y = (point.y + point.vy * delta / 1000 + 1) % 1;
      }
      const x = point.x * width;
      const y = point.y * height;
      for (let j = i + 1; j < nodes.length; j += 1) {
        const other = nodes[j];
        const dx = (point.x - other.x) * width;
        const dy = (point.y - other.y) * height;
        const distance = Math.hypot(dx, dy);
        if (distance > 188) continue;
        context.globalAlpha = (1 - distance / 188) * (0.28 + (Math.sin(seconds * 1.4 + point.phase) + 1) * 0.11);
        context.beginPath();
        context.moveTo(x, y);
        context.lineTo(other.x * width, other.y * height);
        context.stroke();
      }
      const pulse = 0.6 + (Math.sin(seconds * 1.8 + point.phase) + 1) * 0.16;
      context.globalAlpha = pulse;
      context.fillStyle = i % 9 === 0 ? "rgba(245, 190, 111, 0.92)" : i % 3 === 0 ? "rgba(98, 220, 220, 0.9)" : "rgba(167, 235, 193, 0.88)";
      context.beginPath();
      context.arc(x, y, i % 9 === 0 ? 2.1 : 1.65, 0, Math.PI * 2);
      context.fill();
      if (i % 13 === 0) {
        context.strokeStyle = "rgba(98, 220, 220, 0.32)";
        context.beginPath();
        context.moveTo(x - 7, y);
        context.lineTo(x + 7, y);
        context.moveTo(x, y - 7);
        context.lineTo(x, y + 7);
        context.stroke();
      }
    }
    context.globalAlpha = 1;
    if (!staticFrame && !reducedMotion && !stopAnimation) animationFrame = requestAnimationFrame(draw);
  };

  resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(canvas);
  resize();
}

function markAnnouncementFailed() {
  announcementFailed.value = true;
}

onMounted(startBackground);
onUnmounted(() => {
  stopAnimation = true;
  cancelAnimationFrame(animationFrame);
  resizeObserver?.disconnect();
});
</script>

<template>
  <div class="landing-page">
    <canvas ref="backgroundCanvas" class="tech-background" aria-hidden="true"></canvas>
    <main class="landing-main">
      <section class="brand-block" aria-labelledby="landing-title">
        <img class="brand-logo" src="/contact/logo.png" alt="" width="88" height="88" />
        <p class="brand-kicker">LOCAL AI CREATION PLATFORM</p>
        <h1 id="landing-title">VideoFree Studio</h1>
        <p class="brand-subtitle">{{ t("本地 AI 视频创作平台") }}</p>
        <div class="landing-actions">
          <button class="primary-action" type="button" @click="$emit('enter')">
            {{ t("进入工作台") }}
            <Icon icon="solar:arrow-right-linear" width="18" />
          </button>
          <a class="secondary-action" href="https://www.videofreestudio.com/" target="_blank" rel="noopener noreferrer">
            <Icon icon="solar:global-linear" width="17" />
            {{ t("访问官网") }}
          </a>
        </div>
      </section>

      <section class="announcement-section" aria-labelledby="announcement-title">
        <div class="section-heading">
          <div>
            <span class="section-label">VideoFree Studio</span>
            <h2 id="announcement-title">{{ t("公告") }}</h2>
          </div>
          <a href="https://www.videofreestudio.com/" target="_blank" rel="noopener noreferrer" :title="t('访问官网')">
            <Icon icon="solar:arrow-up-right-linear" width="18" />
          </a>
        </div>
        <div class="announcement-frame">
          <iframe
            :title="t('VideoFree Studio 公告')"
            src="https://www.videofreestudio.com/videofree/announcement"
            loading="lazy"
            referrerpolicy="strict-origin-when-cross-origin"
            @error="markAnnouncementFailed"
          ></iframe>
          <div v-if="announcementFailed" class="announcement-fallback">
            <Icon icon="solar:cloud-cross-linear" width="24" />
            <p>{{ t("公告暂时无法加载") }}</p>
            <a href="https://www.videofreestudio.com/" target="_blank" rel="noopener noreferrer">{{ t("打开官网查看") }}</a>
          </div>
        </div>
      </section>
    </main>

    <footer class="landing-footer">
      <a href="mailto:459082139@qq.com">459082139@qq.com</a>
      <a href="https://github.com/linpengishero/VideoFreeStudio" target="_blank" rel="noopener noreferrer" :aria-label="t('GitHub 源码仓库')">
        <Icon icon="mdi:github" width="15" />
        GitHub
      </a>
      <a href="https://gitee.com/heroofgod_admin/videofreestudio" target="_blank" rel="noopener noreferrer" :aria-label="t('码云源码仓库')">
        <Icon icon="simple-icons:gitee" width="15" />
        Gitee
      </a>
      <span>© 2026 VideoFree Studio · v{{ version }}</span>
    </footer>
  </div>
</template>

<style scoped>
.landing-page { position: relative; min-height: 100%; overflow: auto; isolation: isolate; background: #111412; color: #f1f5f0; font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif; letter-spacing: 0; }
.landing-page *, .landing-page *::before, .landing-page *::after { box-sizing: border-box; }
.tech-background { position: fixed; inset: 0; z-index: 0; width: 100%; height: 100%; pointer-events: none; }
.landing-main, .landing-footer { position: relative; z-index: 1; }
.landing-main { width: min(900px, calc(100% - 40px)); margin: 0 auto; padding: clamp(54px, 10vh, 110px) 0 42px; }
.brand-block { display: flex; flex-direction: column; align-items: center; text-align: center; }
.brand-logo { width: 88px; height: 88px; object-fit: contain; margin-bottom: 22px; }
.brand-kicker { margin: 0 0 8px; color: #9bb0a2; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
.brand-block h1 { margin: 0; font-size: 60px; font-weight: 650; line-height: 1; text-shadow: 0 0 22px rgba(74, 204, 203, 0.2); }
.brand-subtitle { margin: 15px 0 0; color: #a8b4aa; font-size: 15px; }
.landing-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin-top: 28px; }
.primary-action, .secondary-action { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 40px; padding: 0 16px; border-radius: 5px; font: inherit; font-size: 13px; text-decoration: none; cursor: pointer; }
.primary-action { border: 1px solid #b7e8c5; background: #b7e8c5; color: #17231b; font-weight: 650; }
.primary-action:hover { background: #d0f5da; border-color: #d0f5da; }
.secondary-action { border: 1px solid #3a4940; background: transparent; color: #c2d3c7; }
.secondary-action:hover { border-color: #9dd5ae; color: #d9f5df; }
.announcement-section { margin-top: 72px; padding-top: 20px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-heading h2 { margin: 5px 0 0; font-size: 17px; font-weight: 600; }
.section-heading a { display: grid; place-items: center; width: 32px; height: 32px; color: #a9c7b1; text-decoration: none; }
.section-heading a:hover { color: #d5f5dc; }
.section-label { color: #91cda1; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; }
.announcement-frame { position: relative; height: 250px; overflow: hidden; border: 1px solid #2e3b32; border-radius: 7px; background: #171d19; }
.announcement-frame iframe { display: block; width: 100%; height: 100%; border: 0; background: transparent; }
.announcement-fallback { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; gap: 8px; padding: 20px; background: #171d19; color: #9eaca2; text-align: center; }
.announcement-fallback p { margin: 0; font-size: 13px; }
.announcement-fallback a { color: #b7e8c5; font-size: 13px; text-decoration: none; }
.announcement-fallback a:hover { text-decoration: underline; }
.landing-footer { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 10px 22px; padding: 20px 20px 28px; color: #76847a; font-size: 12px; }
.landing-footer a { color: #9bb9a2; text-decoration: none; }
.landing-footer a[href^="https://"] { display: inline-flex; align-items: center; gap: 5px; }
.landing-footer a:hover { color: #d1f1d9; text-decoration: underline; }
@media (max-width: 520px) { .landing-main { width: min(100% - 28px, 900px); padding-top: 48px; } .brand-block h1 { font-size: 38px; } .announcement-section { margin-top: 56px; } .announcement-frame { height: 220px; } }
@media (max-width: 360px) { .brand-block h1 { font-size: 32px; } }
</style>
