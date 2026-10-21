<!--
Copyright (c) 2026 VideoFree Studio individual project author and contributors.
Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
-->

<script setup>
defineProps({ items: { type: Array, required: true }, modelValue: { type: String, required: true } })
defineEmits(['update:modelValue'])
</script>

<template>
  <nav class="mode-tabs-dark">
    <button v-for="item in items" :key="item.value"
      :class="{ active: modelValue === item.value }"
      @click="$emit('update:modelValue', item.value)">{{ item.label }}</button>
  </nav>
</template>
