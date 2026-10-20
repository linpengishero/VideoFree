<script setup>
import { displayError, usePluginI18n } from '@framework/services/i18n';
const { t } = usePluginI18n('minimax-music');

import { computed, ref, watch } from 'vue';
import PluginDialog from '@framework/components/PluginDialog.vue';

const props = defineProps({ session: Object, busy: Boolean, pending: Boolean, canAnswer: Boolean, answer: String });
const emit = defineEmits(['update:answer','confirm','answer','new-task']);
const confirmationOpen = ref(false), confirmationLanguage = ref('zh');
const confirmationText = computed(() => confirmationLanguage.value === 'zh' ? props.session?.confirmation?.confirmed_prompt_zh : props.session?.confirmation?.execution_prompt_en);
watch(() => props.session?.id, () => { confirmationOpen.value = false; confirmationLanguage.value = 'zh'; }, { immediate: true });
</script>
<template>
  <section v-if="session" class="collaboration-ui" aria-live="polite">
    <header><span class="status-dot" :class="session.status"/><strong>{{ t(session.message || session.status) }}</strong></header>
    <p v-if="session.error" class="error" role="alert">{{ displayError(session.error) }}</p>
    <ul v-if="session.progress?.stages?.length" class="stages"><li v-for="stage in session.progress.stages" :key="stage.id"><i :class="stage.status"/>{{ t(stage.label) }}<small>{{ t(stage.message || stage.status) }}</small></li></ul>
    <div v-if="session.questions?.length" class="questions"><p v-for="(question,index) in session.questions" :key="index">{{typeof question==='string'?question:question.text || question.question || JSON.stringify(question)}}</p><textarea :value="answer" :disabled="!canAnswer" rows="2" :placeholder="t(&quot;补充说明&quot;)" @input="emit('update:answer',$event.target.value)"/><button type="button" :disabled="!canAnswer || !answer?.trim()" @click="emit('answer')">{{ t("回复") }}</button></div>
    <div v-if="session.confirmation" class="confirmation"><pre>{{session.confirmation.confirmed_prompt_zh}}</pre><pre>{{session.confirmation.execution_prompt_en}}</pre><button class="view-confirmation" type="button" @click="confirmationLanguage='zh';confirmationOpen=true">{{ t("放大查看") }}</button><button type="button" :disabled="busy" @click="emit('confirm')">{{ t("确认并生成") }}</button></div>
  </section>
  <PluginDialog :open="confirmationOpen" :title="t(&quot;生成方案&quot;)" @close="confirmationOpen=false">
    <div class="confirmation-viewer">
      <div class="confirmation-tabs" role="tablist" :aria-label="t(&quot;确认稿语言&quot;)">
        <button v-if="session?.confirmation?.confirmed_prompt_zh" type="button" role="tab" :aria-selected="confirmationLanguage==='zh'" :class="{active:confirmationLanguage==='zh'}" @click="confirmationLanguage='zh'">{{ t("中文确认稿") }}</button>
        <button v-if="session?.confirmation?.execution_prompt_en" type="button" role="tab" :aria-selected="confirmationLanguage==='en'" :class="{active:confirmationLanguage==='en'}" @click="confirmationLanguage='en'">{{ t("英文执行稿") }}</button>
      </div>
      <pre class="confirmation-full-text">{{confirmationText}}</pre>
    </div>
  </PluginDialog>
</template>
<style scoped>.collaboration-ui{box-sizing:border-box;flex:1;height:100%;min-height:0;overflow:auto;display:grid;gap:10px;padding:14px 18px;border-top:1px solid #ffffff18;background:#181b1d;color:#dfe6de;font-size:12px}.collaboration-ui header{display:flex;align-items:center;gap:8px}.status-dot{width:8px;height:8px;border-radius:50%;background:#9ba39a}.status-dot.queued,.status-dot.running{background:#d8b45f}.status-dot.awaiting_confirmation{background:#b7f34a}.status-dot.failed{background:#ed8b83}.error{margin:0;color:#f0a09a}.stages{display:grid;gap:6px;margin:0;padding:0;list-style:none}.stages li{display:flex;align-items:center;gap:7px;color:#abb5aa}.stages i{width:6px;height:6px;border-radius:50%;background:#727b72}.stages i.running{background:#d8b45f}.stages i.completed{background:#b7f34a}.stages small{margin-left:auto;color:#7e897e}.questions,.confirmation{display:grid;gap:8px}.questions p{margin:0}.questions textarea{width:100%;resize:vertical;padding:8px;border:1px solid #ffffff20;border-radius:6px;background:#111415;color:inherit}.questions button,.confirmation button{justify-self:start;padding:7px 11px;border:1px solid #ffffff20;border-radius:6px;background:#2b3727;color:#d9f7b7}.confirmation pre{max-height:130px;margin:0;padding:9px;overflow:auto;white-space:pre-wrap;border-radius:6px;background:#111415;color:#bbc6bb;font:11px/1.6 ui-monospace,Consolas,monospace}.view-confirmation{color:#d9f7b7}.confirmation-viewer{min-width:min(580px,calc(100vw - 64px));max-width:100%}.confirmation-tabs{display:flex;gap:4px;padding:12px 16px 0}.confirmation-tabs button{padding:7px 10px;border:1px solid transparent;border-radius:6px;background:transparent;color:#9aa199;font-size:12px;cursor:pointer}.confirmation-tabs button.active{border-color:#ffffff20;background:#2a2d2e;color:#dfe6de}.confirmation-full-text{max-height:min(62dvh,560px);margin:12px 16px 16px;padding:14px;border:1px solid #ffffff16;border-radius:8px;background:#111315;color:#e0e5dd;font:12px/1.75 ui-monospace,Consolas,monospace;white-space:pre-wrap;overflow:auto;overscroll-behavior:contain;scrollbar-width:none}.confirmation-full-text::-webkit-scrollbar{display:none}.collaboration-ui button:disabled,.questions textarea:disabled{opacity:.5;cursor:default}</style>
