(function () {
  const panel = document.getElementById('coinReviewPanel');
  if (!panel?.dataset.url) return;
  const buttons = Array.from(panel.querySelectorAll('[data-review-action]'));
  const error = panel.querySelector('.coin-review-error');
  let pending = false;
  buttons.forEach(button => button.addEventListener('click', async () => {
    if (pending) return;
    pending = true;
    buttons.forEach(b => { b.disabled = true; });
    error.hidden = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(panel.dataset.url, {
        method: 'POST', credentials: 'same-origin', signal: controller.signal,
        body: new URLSearchParams({
          csrf_token: panel.dataset.csrf, review_token: panel.dataset.reviewToken,
          action: button.dataset.reviewAction,
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || typeof result.dismissed !== 'boolean') {
        throw new Error(result.error || 'Could not update the review. Reload the page and try again.');
      }
      panel.querySelector('[data-review-open]').hidden = result.dismissed;
      panel.querySelector('[data-review-dismissed]').hidden = !result.dismissed;
      buttons.forEach(b => { b.disabled = false; });
      panel.querySelector(`[data-review-action="${result.dismissed ? 'restore' : 'dismiss'}"]`).focus();
    } catch (err) {
      error.textContent = err.name === 'AbortError'
        ? 'The review update has not been confirmed. Retry or reload to check its status.'
        : (err instanceof TypeError ? 'Could not reach Stuff. Retry when the connection is restored.' : err.message);
      error.hidden = false;
    } finally {
      clearTimeout(timeout);
      pending = false;
      buttons.forEach(b => { b.disabled = false; });
    }
  }));
})();
