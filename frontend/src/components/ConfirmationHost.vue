<!--
Copyright (c) 2026 VideoFree individual project author and contributors.
Part of VideoFree: https://github.com/linpengishero/VideoFree
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import { onMounted, onBeforeUnmount, ref, nextTick } from 'vue';
import PluginDialog from './PluginDialog.vue';
const current = ref(null);
const queue = [];
let disposed = false;
let advancing = false;
function receive(event) {
  const request = event.detail;
  if (!request || typeof request.resolve !== 'function' || request.handled) return;
  request.handled = true;
  queue.push(request);
  if (!current.value && !advancing) current.value = queue.shift();
}
async function settle(value) {
  const request = current.value;
  if (!request) return;
  advancing = true;
  current.value = null;
  request.resolve(value);
  await nextTick();
  advancing = false;
  if (!disposed) current.value = queue.shift() || null;
}
onMounted(() => window.addEventListener('videofree:confirm', receive));
onBeforeUnmount(() => {
  disposed = true;
  window.removeEventListener('videofree:confirm', receive);
  current.value?.resolve(false);
  queue.splice(0).forEach(request => request.resolve(false));
});
</script>
<template>
  <PluginDialog :open="!!current" :title="current?.title" @close="settle(false)">
    <p class="confirmation-message">{{ current?.message }}</p>
    <template #footer>
      <button class="ui-button" type="button" autofocus @click="settle(false)">{{ t('取消') }}</button>
      <button class="ui-button" :class="current?.danger ? 'is-danger' : 'is-primary'" type="button" @click="settle(true)">{{ current?.confirmText }}</button>
    </template>
  </PluginDialog>
</template>
<style scoped>
.confirmation-message{margin:0;padding:22px 20px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7;font-size:14px}
</style>
