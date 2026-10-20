<!--
Copyright (c) 2026 VideoFree individual project author and contributors.
Part of VideoFree: https://github.com/linpengishero/VideoFree
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { onMounted, onUnmounted, ref } from 'vue';

const notices = ref([]);
const timers = new Map();
const target = ref('body');
let observer;

// Native modal dialogs make elements outside them inert, regardless of z-index.
function updateTarget() {
  target.value = [...document.querySelectorAll('dialog[open]')].at(-1) || 'body';
}

function remove(id) {
  notices.value = notices.value.filter(item => item.id !== id);
  const timer = timers.get(id);
  if (timer) clearTimeout(timer);
  timers.delete(id);
}
function add(event) {
  const notice = event.detail;
  if (!notice?.id || !notice.message) return;
  remove(notice.id);
  if (notices.value.length >= 5) remove(notices.value[0].id);
  notices.value.push(notice);
  if (notice.duration > 0) timers.set(notice.id, setTimeout(() => remove(notice.id), notice.duration));
}
function dismiss(event) { remove(event.detail?.id); }

onMounted(() => {
  updateTarget();
  observer = new MutationObserver(updateTarget);
  observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['open'] });
  window.addEventListener('videofree:notification', add);
  window.addEventListener('videofree:notification:dismiss', dismiss);
});
onUnmounted(() => {
  observer?.disconnect();
  window.removeEventListener('videofree:notification', add);
  window.removeEventListener('videofree:notification:dismiss', dismiss);
  timers.forEach(timer => clearTimeout(timer));
  timers.clear();
});
</script>

<template>
  <Teleport :to="target">
  <div class="notification-host" aria-live="polite" aria-atomic="false" @click.stop @pointerdown.stop>
    <article v-for="notice in notices" :key="notice.id" class="notification" :class="`is-${notice.type}`" role="status">
      <div class="notification-copy"><strong v-if="notice.title">{{ notice.title }}</strong><span>{{ notice.message }}</span></div>
      <button type="button" :aria-label="t(&quot;关闭通知&quot;)" :title="t(&quot;关闭通知&quot;)" @click="remove(notice.id)">×</button>
    </article>
  </div>
  </Teleport>
</template>

<style scoped>
.notification-host{position:fixed;top:72px;right:18px;z-index:10050;display:grid;gap:8px;width:min(380px,calc(100vw - 36px));pointer-events:none}.notification{display:flex;align-items:flex-start;gap:10px;padding:12px 12px 12px 14px;border:1px solid #ffffff22;border-radius:9px;background:#202522f5;color:#e8eee6;box-shadow:0 14px 40px #0009;pointer-events:auto;animation:notification-in .18s ease-out}.notification.is-error{border-color:#e17e7866}.notification.is-success{border-color:#a9dc7266}.notification.is-info{border-color:#8bb8d966}.notification-copy{display:grid;gap:3px;min-width:0;flex:1;font-size:12px;line-height:1.5}.notification-copy strong{font-size:11px;color:#b7f34a}.notification-copy span{overflow-wrap:anywhere}.notification button{flex:none;width:24px;height:24px;padding:0;border:0;border-radius:5px;background:transparent;color:#aab3aa;font-size:20px;line-height:20px;cursor:pointer}.notification button:hover{background:#ffffff10;color:#fff}@keyframes notification-in{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
</style>
