<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import PluginDialog from './PluginDialog.vue';
defineProps({open:Boolean, busy:Boolean});
const emit = defineEmits(['close']);
</script>
<template>
  <PluginDialog :open="open" :busy="busy" :framed="false" @close="emit('close')"><slot /></PluginDialog>
</template>
