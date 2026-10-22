/*
 * Copyright (c) 2026 VideoFree Studio individual project author and contributors.
 * Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
 * Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
 * Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
 */

export function getValue(values, bind) {
  return bind.split('.').reduce((value, key) => value?.[key], values);
}

export function setValue(values, bind, value) {
  const parts = bind.split('.');
  const target = parts.length === 2 ? (values[parts[0]] ||= {}) : values;
  target[parts.at(-1)] = value;
}

export function defaults(ui) {
  const result = {settings: {}, parameters: {}};
  for (const field of ui?.fields || []) {
    if (field.component !== 'media' && field.default !== undefined) setValue(result, field.bind, field.default);
  }
  return result;
}

export function restoreActionInputs(ui, saved, requestParams = {}) {
  const base = defaults(ui);
  const result = {...base, ...(saved || {}),
    settings: {...base.settings, ...(saved?.settings || {})},
    parameters: {...base.parameters, ...(saved?.parameters || {})}};
  if (saved && typeof saved === 'object' && Object.keys(saved).length) return result;

  for (const field of ui?.fields || []) {
    if (field.component === 'dimensions') {
      const width = Number(requestParams.width), height = Number(requestParams.height);
      if (width > 0 && height > 0) setValue(result, field.bind, `${width}x${height}`);
      continue;
    }
    const parts = field.bind.split('.');
    const value = parts.length === 2
      ? parts[0] === 'settings'
        ? requestParams.api_settings?.[parts[1]]
        : requestParams.plugin_parameters?.[parts[1]] ?? requestParams.parameters?.[parts[1]]
      : requestParams[field.bind]
        ?? (field.bind === 'preset_id' ? requestParams.character : undefined)
        ?? (field.bind === 'voice_description' ? requestParams.instruction : undefined);
    if (value !== undefined) setValue(result, field.bind, value);
  }
  return result;
}

export function collectActionInputs(ui, values, saved = {}) {
  const result = JSON.parse(JSON.stringify(saved || {}));
  for (const field of ui?.fields || []) {
    if (field.component === 'dimensions') {
      const match = String(getValue(values, field.bind) || '').match(/^(\d+)x(\d+)$/i);
      if (match) {
        result.width = Number(match[1]);
        result.height = Number(match[2]);
      }
      continue;
    }
    const value = getValue(values, field.bind);
    if (value !== undefined) setValue(result, field.bind, value);
  }
  return result;
}

export function fieldOptions(field, source) {
  if (field.component !== 'dimensions') return field.options || [];
  const width = Number(source?.request?.params?.latent_width || source?.width || 16);
  const height = Number(source?.request?.params?.latent_height || source?.height || 9);
  const ratio = width / height;
  const alignment = field.alignment;
  const result = [];
  for (const preset of field.presets || []) {
    const scale = preset.edge / (preset.long_edge ? Math.max(width, height) : Math.min(width, height));
    const idealWidth = width * scale, idealHeight = height * scale;
    let best;
    for (let w = Math.max(1, Math.round(idealWidth / alignment) - 4); w <= Math.round(idealWidth / alignment) + 4; w++) {
      for (let h = Math.max(1, Math.round(idealHeight / alignment) - 4); h <= Math.round(idealHeight / alignment) + 4; h++) {
        const targetWidth = w * alignment, targetHeight = h * alignment;
        const score = Math.abs(targetWidth / targetHeight - ratio) / ratio
          + 0.125 * (Math.abs(targetWidth - idealWidth) / idealWidth + Math.abs(targetHeight - idealHeight) / idealHeight);
        if (!best || score < best.score) best = {width: targetWidth, height: targetHeight, score};
      }
    }
    if (best.width < width || best.height < height) continue;
    const value = `${best.width}x${best.height}`;
    if (!result.some(item => item.value === value)) result.push({value, label: `${preset.label} · ${best.width} × ${best.height}`});
  }
  return result;
}
