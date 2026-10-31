/* Quick entry uses the existing exact eBay order importer. */
(() => {
  'use strict';
  const orderDialog = document.getElementById('banknoteOrderDialog');
  const orderAdd = document.getElementById('banknoteOrderAdd');
  if (orderDialog && orderAdd) {
    const form = document.getElementById('banknoteOrderForm');
    const input = document.getElementById('banknoteOrderNumber');
    const process = document.getElementById('banknoteOrderProcess');
    const cancel = document.getElementById('banknoteOrderCancel');
    const status = document.getElementById('banknoteOrderStatus');
    let processing = false;
    const say = (message, error = false) => {
      status.textContent = message;
      status.dataset.error = String(error);
    };
    orderAdd.addEventListener('click', () => {
      say(''); orderDialog.showModal(); input.focus();
    });
    cancel.addEventListener('click', () => orderDialog.close());
    orderDialog.addEventListener('cancel', event => {
      if (processing) event.preventDefault();
    });
    orderDialog.addEventListener('close', () => orderAdd.focus());
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (processing) return;
      if (!input.value.trim()) {
        say('Enter the eBay order number first.', true); input.focus(); return;
      }
      processing = true; process.disabled = true; cancel.disabled = true;
      input.readOnly = true; form.setAttribute('aria-busy', 'true');
      say('Retrieving eBay order…');
      try {
        const batch = await window.startBanknoteOrderReview(input.value,
          {onProgress: message => say(message)});
        window.location.assign(batch.url);
      } catch (error) {
        say(error.message, true);
        processing = false; process.disabled = false; cancel.disabled = false;
        input.readOnly = false; form.removeAttribute('aria-busy'); input.focus();
      }
    });
  }
})();
