
import { t } from '../services/i18n';
/*
 * Copyright (c) 2026 VideoFree Studio individual project author and contributors.
 * Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
 * Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
 * Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.
 */

// Events keep independently bundled plugins on the same host confirmation queue.
export function confirmAction(message, { title = t('请确认'), confirmText = t('确认'), danger = true } = {}) {
  return new Promise(resolve => {
    const request = { message: String(message), title, confirmText, danger, resolve, handled: false };
    window.dispatchEvent(new CustomEvent('videofree:confirm', { detail: request }));
    if (!request.handled) resolve(false);
  });
}
