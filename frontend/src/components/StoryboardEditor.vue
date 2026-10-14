<script setup>
import { Icon } from "@iconify/vue";
defineProps({ referenceLabels: { type: Array, required: true } });
const shots = defineModel("shots", { type: Array });
const references = defineModel("references", { type: Array });
function select(event, index) {
  references.value = references.value.map((v, i) =>
    i === index ? event.target.files[0] || null : v,
  );
}
</script>
<template>
  <div class="story-editor">
    <div class="story-refs">
      <label v-for="(name, i) in referenceLabels" :key="name"
        ><span>{{ name }}</span
        ><span class="story-file"
          ><Icon icon="solar:add-circle-linear" width="20" />{{
            references[i]?.name || "选择参考图"
          }}</span
        ><input type="file" accept="image/*" @change="select($event, i)"
      /></label>
    </div>
    <div class="story-shots">
      <label v-for="(_, i) in shots" :key="i"
        ><span>镜头 {{ i + 1 }}</span
        ><textarea
          :value="shots[i]"
          @input="
            shots = shots.map((v, j) => (j === i ? $event.target.value : v))
          "
          placeholder="描述画面、动作与机位"
        />
      </label>
    </div>
  </div>
</template>
<style scoped>
.story-editor {
  width: 100%;
  min-width: 0;
}
.story-refs {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.story-editor label {
  display: grid;
  gap: 6px;
  min-width: 0;
  color: #aeb5bd;
  font-size: 12px;
}
.story-file {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  border: 1px dashed #ffffff40;
  padding: 10px;
  border-radius: 6px;
  cursor: pointer;
}
.story-refs input {
  display: none;
}
.story-shots {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.story-shots textarea {
  width: 100%;
  height: 70px;
  padding: 8px;
  resize: none;
  border: 1px solid #ffffff20;
  border-radius: 6px;
  background: #131518;
  color: #e4e7eb;
}
@media (max-width: 600px) {
  .story-shots {
    gap: 6px;
  }
  .story-file {
    padding: 6px;
    font-size: 11px;
  }
}
</style>
