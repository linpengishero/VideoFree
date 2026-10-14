<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { Icon } from "@iconify/vue";

const props = defineProps({
  active: Boolean,
  open: Boolean,
  busy: Boolean,
  messages: { type: Array, default: () => [] },
  result: { type: Object, default: null },
  progress: { type: Object, default: null },
  activeCount: { type: Number, default: 0 },
  activities: { type: Array, default: () => [] },
  currentSession: { type: String, default: "" },
  error: { type: String, default: "" },
});
const emit = defineEmits(["update:open", "send", "generate", "reset", "cancel", "cancel-all", "open-session", "cancel-session"]);
const input = ref("");
const conversation = ref(null);
const selectedAnswers = ref({});
const waitingSeconds = ref(0);
let waitingTimer = null;
function waitingText(seconds) {
  if (seconds < 60) return `${seconds}秒`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}分${rest}秒` : `${minutes}分钟`;
}
const currentStage = computed(() =>
  props.progress?.stages?.find((stage) => stage.status === "running"),
);
const stateLabel = computed(() =>
  props.busy
    ? `${currentStage.value?.label || "处理中"} · ${waitingText(waitingSeconds.value)}`
    : props.progress?.status === "cancelled"
      ? "已取消"
      : props.result?.submitted
      ? "已提交生成"
      : props.result?.status === "ready"
        ? "方案就绪"
        : props.error
          ? "需要处理"
          : "等待补充",
);
const questions = computed(() =>
  (props.result?.questions || []).filter(
    (question) =>
      question &&
      String(question.text || "").trim() &&
      Array.isArray(question.options) &&
      question.options.length > 0,
  ),
);
const answeredCount = computed(
  () =>
    questions.value.filter(
      (question) => selectedAnswers.value[question.id || question.text],
    ).length,
);
const allQuestionsAnswered = computed(
  () =>
    questions.value.length > 0 &&
    answeredCount.value === questions.value.length,
);
const review = computed(() => props.result?.review || null);
const reviewWarnings = computed(() =>
  Array.isArray(review.value?.warnings) ? review.value.warnings : [],
);

function send(value = input.value) {
  const message = String(value || "").trim();
  if (!message || props.busy) return;
  emit("send", message);
  input.value = "";
}
function answer(question, option) {
  selectedAnswers.value[question.id || question.text] = option;
}
function submitAnswers() {
  if (!allQuestionsAnswered.value || props.busy) return;
  const response = questions.value
    .map(
      (question) =>
        `${question.text}\n我的选择：${selectedAnswers.value[question.id || question.text]}`,
    )
    .join("\n\n");
  selectedAnswers.value = {};
  send(response);
}
watch(
  () => props.busy,
  (busy) => {
    clearInterval(waitingTimer);
    waitingTimer = null;
    waitingSeconds.value = 0;
    if (busy) {
      waitingTimer = setInterval(() => {
        waitingSeconds.value += 1;
      }, 1000);
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => clearInterval(waitingTimer));
watch(
  () => props.result,
  () => {
    selectedAnswers.value = {};
  },
  { deep: true },
);
watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    if (conversation.value)
      conversation.value.scrollTop = conversation.value.scrollHeight;
  },
);
</script>

<template>
  <button
    v-if="active && !open"
    class="agent-reopen"
    type="button"
    aria-label="打开智能协作"
    @click="emit('update:open', true)"
  >
    <Icon icon="solar:stars-minimalistic-bold-duotone" width="20" />
    <span>{{ stateLabel }}</span>
  </button>

  <aside v-if="active && open" class="agent-dock" aria-label="智能协作面板">
    <header class="agent-header">
      <span class="agent-mark"
        ><Icon icon="solar:stars-minimalistic-bold-duotone" width="19"
      /></span>
      <div>
        <strong>智能协作</strong
        ><small><i :class="{ pulse: busy }"></i>{{ stateLabel }}<template v-if="activeCount > 1"> · {{ activeCount }} 项处理中</template></small>
      </div>
      <button
        v-if="activeCount > 1"
        type="button"
        title="取消全部智能协作"
        aria-label="取消全部智能协作"
        @click="emit('cancel-all')"
      >
        <Icon icon="solar:forbidden-circle-linear" width="18" />
      </button>
      <button
        v-if="busy"
        type="button"
        title="取消当前协作"
        aria-label="取消当前协作"
        @click="emit('cancel')"
      >
        <Icon icon="solar:stop-circle-linear" width="18" />
      </button>
      <button
        type="button"
        title="新建会话"
        aria-label="新建会话"
        :disabled="busy"
        @click="emit('reset')"
      >
        <Icon icon="solar:restart-linear" width="18" />
      </button>
      <button
        type="button"
        title="收起"
        aria-label="收起"
        @click="emit('update:open', false)"
      >
        <Icon icon="solar:minimize-square-3-linear" width="18" />
      </button>
    </header>

    <div ref="conversation" class="agent-conversation" aria-live="polite">
      <section v-if="activities.length > 1" class="agent-activity-list">
        <article v-for="item in activities" :key="item.id" :class="{ current: item.id === currentSession }">
          <button type="button" @click="emit('open-session', item.id)">
            <b>{{ item.model }}</b><span>{{ item.mode }} · {{ item.status }}</span>
          </button>
          <button v-if="['queued', 'running'].includes(item.status)" type="button" title="取消此协作" @click="emit('cancel-session', item.id)">
            <Icon icon="solar:stop-circle-linear" width="15" />
          </button>
        </article>
      </section>
      <div
        v-for="(item, index) in messages"
        :key="index"
        class="agent-message"
        :class="`is-${item.role}`"
      >
        <span>{{ item.role === "user" ? "你" : "AI" }}</span>
        <p>{{ item.content }}</p>
      </div>

      <div v-if="busy" class="agent-thinking">
        <i></i><i></i><i></i><span>{{ currentStage?.message || "等待模型响应" }}</span>
      </div>
      <section v-if="progress?.stages?.length" class="agent-stage-list">
        <div
          v-for="stage in progress.stages"
          :key="stage.id"
          :class="`is-${stage.status}`"
        >
          <Icon
            :icon="
              stage.status === 'completed'
                ? 'solar:check-circle-bold'
                : stage.status === 'error'
                  ? 'solar:danger-circle-bold'
                  : stage.status === 'skipped'
                    ? 'solar:minus-circle-linear'
                    : stage.status === 'running'
                      ? 'solar:refresh-circle-linear'
                      : 'solar:circle-linear'
            "
            width="16"
          />
          <span><b>{{ stage.label }}</b><small v-if="stage.message">{{ stage.message }}</small></span>
        </div>
      </section>
      <div v-if="error" class="agent-error">
        <Icon icon="solar:danger-triangle-linear" width="17" />{{ error }}
      </div>

      <section
        v-if="!busy && result?.reference_map?.length"
        class="agent-reference-map"
      >
        <h4>素材关系</h4>
        <div v-for="item in result.reference_map" :key="item.label">
          <b>{{ item.label }}</b
          ><span>{{ item.role }}</span
          ><i :class="`confidence-${item.confidence || 'medium'}`"></i>
        </div>
      </section>

      <section
        v-if="!busy && questions.length"
        class="agent-questions"
      >
        <article
          v-for="question in questions"
          :key="question.id || question.text"
        >
          <p>{{ question.text }}</p>
          <div>
            <button
              v-for="option in question.options || []"
              :key="option"
              type="button"
              :class="{
                selected:
                  selectedAnswers[question.id || question.text] === option,
              }"
              @click="answer(question, option)"
            >
              {{ option }}
            </button>
          </div>
        </article>
        <button
          v-if="allQuestionsAnswered"
          class="agent-submit-answers"
          type="button"
          @click="submitAnswers"
        >
          <Icon icon="solar:check-circle-linear" width="16" />提交全部确认（{{
            answeredCount
          }}/{{ questions.length }}）
        </button>
        <small v-else class="agent-answer-progress"
          >请完成全部选择（{{ answeredCount }}/{{ questions.length }}）</small
        >
      </section>

      <section
        v-if="!busy && result?.status === 'ready' && result.optimized_prompt_zh"
        class="agent-plan agent-confirmation"
      >
        <h4>
          <Icon icon="solar:document-text-linear" width="16" />生成方案确认
        </h4>
        <p>{{ result.optimized_prompt_zh }}</p>
      </section>
      <section
        v-if="!busy && result?.status === 'ready' && review"
        class="agent-review"
        :class="{ 'has-warnings': reviewWarnings.length }"
      >
        <h4>
          <Icon
            :icon="reviewWarnings.length ? 'solar:danger-triangle-linear' : 'solar:check-circle-linear'"
            width="15"
          />
          {{ review.summary || "成稿检查完成" }}
        </h4>
        <ul v-if="reviewWarnings.length">
          <li v-for="warning in reviewWarnings" :key="warning">{{ warning }}</li>
        </ul>
      </section>
    </div>

    <div class="agent-input-wrap">
      <textarea
        v-model="input"
        rows="1"
        placeholder="补充人物、素材关系或镜头要求…"
        @keydown.enter.exact.prevent="send()"
      ></textarea>
      <button
        type="button"
        :disabled="busy || !input.trim()"
        aria-label="发送消息"
        @click="send()"
      >
        <Icon icon="solar:arrow-up-linear" width="18" />
      </button>
    </div>
    <footer v-if="result?.status === 'ready' && !busy">
      <span
        ><Icon
          :icon="reviewWarnings.length ? 'solar:danger-triangle-linear' : 'solar:check-circle-bold'"
          width="16"
        />{{ reviewWarnings.length ? `有 ${reviewWarnings.length} 条提示待确认` : "已完成生成前检查" }}</span
      >
      <button
        type="button"
        :disabled="result.submitted"
        @click="emit('generate')"
      >
        <Icon
          :icon="
            result.submitted
              ? 'solar:check-circle-linear'
              : 'solar:play-circle-linear'
          "
          width="17"
        />{{ result.submitted ? "已提交" : "按此方案生成" }}
      </button>
    </footer>
  </aside>
</template>
