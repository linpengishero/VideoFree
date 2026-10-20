/*
 * Copyright (c) 2026 VideoFree individual project author and contributors.
 * Part of VideoFree: https://github.com/linpengishero/VideoFree
 * Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
 * Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
 */

// Display aliases stay bound to upload IDs for the lifetime of a composer draft.
export function referenceMentions(items, bindings) {
  const names = { image: 'Picture', video: 'Video', audio: 'Audio' }, counts = {};
  const active = new Map();
  for (const item of items) {
    if (!names[item.type]) continue;
    const index = counts[item.type] = (counts[item.type] || 0) + 1;
    if (!bindings.has(item.upload_id)) {
      const name = item.name || item.upload_id;
      let alias = `@${name}`, suffix = 2;
      const used = new Set([...bindings.values()].map(binding => binding.alias));
      while (used.has(alias)) alias = `@${name} (${suffix++})`;
      bindings.set(item.upload_id, { id: item.upload_id, alias, name, type: item.type });
    }
    active.set(item.upload_id, { ...item, label: `<${names[item.type]} ${index}>` });
  }
  // Keep removed aliases reserved: reuploading a same-named file must not rebind text.
  return [...bindings.values()].map(binding => ({ ...active.get(binding.id), ...binding, available: active.has(binding.id) }));
}

export function promptSegments(value, mentions) {
  const text = String(value || ''), aliases = new Map(mentions.map(item => [item.alias, item]));
  if (!aliases.size) return [{ text, mention: false }];
  const escaped = [...aliases.keys()].sort((a, b) => b.length - a.length).map(alias => alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const segments = []; let cursor = 0;
  for (const match of text.matchAll(new RegExp(escaped.join('|'), 'g'))) {
    if (match.index > cursor) segments.push({ text: text.slice(cursor, match.index), mention: false });
    const reference = aliases.get(match[0]);
    segments.push({ text: match[0], mention: true, reference });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length || !segments.length) segments.push({ text: text.slice(cursor), mention: false });
  return segments;
}
