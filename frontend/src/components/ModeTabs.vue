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
