// Events keep independently bundled plugins on the same host confirmation queue.
export function confirmAction(message, { title = '请确认', confirmText = '确认', danger = true } = {}) {
  return new Promise(resolve => {
    const request = { message: String(message), title, confirmText, danger, resolve, handled: false };
    window.dispatchEvent(new CustomEvent('videofree:confirm', { detail: request }));
    if (!request.handled) resolve(false);
  });
}
