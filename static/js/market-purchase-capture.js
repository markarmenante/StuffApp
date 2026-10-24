(() => {
  const panel = document.getElementById('marketPurchaseCapture');
  if (!panel) return;
  const message = panel.querySelector('[data-capture-message]');
  const input = document.querySelector('#mainForm [name="order_number"]');
  const marketplace = document.querySelector('#mainForm [name="marketplace"]');
  const edited = new Set();
  for (const field of [input, marketplace]) {
    field?.addEventListener('input', () => edited.add(field));
    field?.addEventListener('change', () => edited.add(field));
  }
  let state = JSON.parse(panel.querySelector('[data-capture-initial]').textContent);
  let busy = false, timer;
  const active = () => ['queued', 'reading', 'waiting', 'sign_in_required', 'challenge_required'].includes(state.status);
  function render(next) {
    state = next;
    message.textContent = state.message || 'Waiting for your eBay purchase confirmation.';
    const order = state.order_reference;
    if (state.status !== 'done' || !order?.number) return;
    if (input && !edited.has(input) && !input.value.trim()) {
      input.value = order.number;
      const link = input.closest('.purchase-order-cell')?.querySelector('.purchase-order-link');
      if (link && order.url) {
        link.href = order.url; link.hidden = false;
        link.title = `Open eBay order ${order.number}`;
        link.setAttribute('aria-label', link.title);
      }
    }
    if (marketplace && !edited.has(input) && (!input || !input.value.trim() || input.value === order.number)
        && !edited.has(marketplace) && !marketplace.value) marketplace.value = 'eBay';
    document.dispatchEvent(new CustomEvent('purchase-sources-updated'));
  }
  async function refresh() {
    clearTimeout(timer);
    if (busy || !active()) return;
    if (document.hidden) { timer = setTimeout(refresh, 10000); return; }
    busy = true;
    try {
      const response = await fetch(panel.dataset.statusUrl, {
        cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(10000),
      });
      if (response.ok) render(await response.json());
    } catch (_) { /* A transient read failure must not interrupt editing. */ }
    finally { busy = false; if (active()) timer = setTimeout(refresh, 10000); }
  }
  render(state);
  window.addEventListener('focus', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  if (active()) refresh();
})();
