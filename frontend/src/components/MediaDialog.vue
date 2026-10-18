<script setup>
import PluginDialog from './PluginDialog.vue';
defineProps({open:Boolean, busy:Boolean});
const emit = defineEmits(['close']);
</script>
<template>
  <PluginDialog :open="open" :busy="busy" :framed="false" @close="emit('close')"><slot /></PluginDialog>
</template>
