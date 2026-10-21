import { computed, inject, provide, ref } from 'vue';
import zh from '../locales/zh-CN.json';
import en from '../locales/en-US.json';

export const locale = ref('en-US');
const plugins = ref({});
export const UI_CONTEXT = 'videofree:ui-context';
const supported = value => value === 'en-US' ? value : 'zh-CN';

export function setLocale(value) {
  locale.value = supported(value);
  if (typeof document !== 'undefined') document.documentElement.lang = locale.value;
}
export function registerPluginMessages(items) {
  plugins.value = Object.fromEntries(items.map(item => [item.id, {
    defaultLocale: item.localization?.default_locale || 'zh-CN', messages: item.ui_messages || {},
  }]));
}
function interpolate(text, values) {
  return String(text).replace(/\{(\w+)\}/g, (match, key) => Object.hasOwn(values, key) ? String(values[key]) : match);
}
export function translate(language, pluginId, key, fallback = key, values = {}) {
  const plugin = plugins.value[pluginId];
  const messages = plugin?.messages;
  const text = pluginId
    ? messages?.[language]?.[key] ?? messages?.[plugin.defaultLocale]?.[key] ?? fallback
    : (language === 'en-US' ? en[key] : zh[key]) ?? zh[key] ?? fallback;
  return interpolate(text, values);
}
export const t = (key, fallback = key, values = {}) => translate(locale.value, '', key, fallback, values);
export const pluginT = id => (key, fallback = key, values = {}) => translate(locale.value, id, key, fallback, values);

// Keep third-party diagnostics intact when no curated translation is available.
export function displayError(detail, status) {
  const text = String(detail || '');
  const translated = t(text);
  if (translated !== text || locale.value !== 'en-US' || !/[\u3400-\u9fff]/u.test(text)) return translated;
  const summary = {401: 'Authentication required', 403: 'Access denied', 404: 'Not found', 409: 'Operation unavailable in the current state', 422: 'Invalid request'}[status] || 'Operation failed';
  return summary + ' — ' + text;
}

export function providePluginI18n(pluginId) {
  const language = computed(() => locale.value);
  const context = { locale: language, t: (key, fallback = key, values = {}) => translate(language.value, pluginId.value, key, fallback, values) };
  provide(UI_CONTEXT, context);
  return context;
}
export function usePluginI18n(pluginId) {
  return inject(UI_CONTEXT, null) || { locale, t: pluginT(pluginId) };
}

// Only declaration-owned presentation fields are localized. IDs, defaults, prompts,
// input schemas and user-authored content are never traversed as display text.
const displayFields = ['name', 'label', 'description', 'placeholder', 'help', 'title', 'selection_label', 'mode_name', 'model_name', 'provider_name'];
const childFields = ['ui', 'fields', 'options', 'presets', 'processing_modes', 'selector_model', 'functions', 'schema', 'variants'];
export function localizeDeclaration(value, pluginId = value?.plugin_id || value?.id || '') {
  if (Array.isArray(value)) return value.map(item => localizeDeclaration(item, pluginId));
  if (!value || typeof value !== 'object') return value;
  const result = { ...value };
  for (const field of displayFields) {
    if (typeof value[`${field}_key`] === 'string') result[field] = translate(locale.value, pluginId, value[`${field}_key`], value[field] || '');
  }
  for (const field of childFields) if (value[field]) result[field] = localizeDeclaration(value[field], pluginId);
  if (result.icon_text && result.name) result.icon_text = [...result.name][0];
  return result;
}

// Wrap fixed UI label tables, never user data. Getters keep labels reactive even
// when a table is declared outside a component's setup function.
export function localizedLabels(value, translator = t) {
  const cache = new WeakMap();
  const wrap = target => {
    if (!target || typeof target !== 'object') return target;
    if (cache.has(target)) return cache.get(target);
    const proxy = new Proxy(target, { get(object, key, receiver) {
      const result = Reflect.get(object, key, receiver);
      return typeof result === 'string' ? translator(result) : typeof result === 'object' ? wrap(result) : result;
    } });
    cache.set(target, proxy);
    return proxy;
  };
  return wrap(value);
}
