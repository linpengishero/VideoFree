/*
 * Copyright (c) 2026 VideoFree individual project author and contributors.
 * Part of VideoFree: https://github.com/linpengishero/VideoFree
 * Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
 * Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
 */

const EVENT = 'videofree:notification';
let nextId = 1;

/** Notify the framework without coupling a plugin to the host component tree. */
export function notify(message, options = {}) {
  if (typeof window === 'undefined') return '';
  const text = typeof message === 'string' ? message : String(message ?? '');
  if (!text.trim()) return '';
  const detail = {
    id: `notice-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}-${nextId++}`}`,
    message: text,
    title: options.title || '',
    type: ['error', 'success', 'info'].includes(options.type) ? options.type : 'error',
    duration: Number.isFinite(options.duration) ? Math.max(0, options.duration) : 4500,
  };
  window.dispatchEvent(new CustomEvent(EVENT, { detail }));
  return detail.id;
}

export function dismissNotification(id) {
  if (typeof window !== 'undefined' && id) {
    window.dispatchEvent(new CustomEvent(`${EVENT}:dismiss`, { detail: { id } }));
  }
}
