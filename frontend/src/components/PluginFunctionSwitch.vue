<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
import { t } from '../services/i18n';

import {computed} from 'vue';
const props = defineProps({capabilities:Array, selected:Object, disabled:Boolean});
const emit = defineEmits(['select']);
const options = computed(() => (props.capabilities || []).filter(item =>
  item.operation !== 'postprocess' && item.selector_model &&
  item.category === props.selected?.category &&
  item.selector_model.plugin_id === props.selected?.selector_model?.plugin_id &&
  item.selector_model.id === props.selected?.selector_model?.id
).sort((a,b) => (a.selector_order || 0) - (b.selector_order || 0) || a.id.localeCompare(b.id)).map(item => ({value:item.id,label:item.mode_name})));
</script>
<template>
  <div class="plugin-function-switch" :inert="disabled || undefined" :aria-label="t(&quot;生成子功能&quot;)">
    <div role="tablist" :aria-label="t(&quot;生成子功能&quot;)">
      <button v-for="option in options" :key="option.value" type="button" role="tab" :aria-selected="option.value===selected?.id" :class="{active:option.value===selected?.id}" @click="emit('select',option.value)">{{option.label}}</button>
    </div>
  </div>
</template>
<style scoped>
.plugin-function-switch{min-width:0;max-width:100%}
[role=tablist]{display:flex;flex-wrap:wrap;justify-content:flex-start;gap:4px}
button{min-height:30px;padding:6px 11px;background:transparent;color:#858b84;border:1px solid transparent;border-radius:7px;font-size:12px;line-height:1.2;cursor:pointer}
button:hover{background:#ffffff08;color:#d5d9d2}
button.active{background:#303234;border-color:#ffffff20;color:#edf1e9}
button:focus-visible{outline:1px solid var(--lime)}
</style>
