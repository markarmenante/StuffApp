/* One purchase phase. Ownership is a deliberate inspection action. */
(() => {
  const pill = document.querySelector('[data-purchase-status-control]');
  const initial = document.querySelector('[data-purchase-status-initial]');
  const select = document.querySelector('#mainForm select[name="status"]');
  if (!pill || !initial || !select) return;
  let state = JSON.parse(initial.textContent), busy = false;
  const readOnly = pill.disabled;
  const notice = document.querySelector('[data-purchase-status-notice]');
  const message = notice?.querySelector('[data-purchase-status-message]');
  const feedbackLink = notice?.querySelector('[data-purchase-feedback-link]');
  const review = document.querySelector('[data-purchase-status-review]');
  const phases = ['Ordered', 'Shipped', 'Delivered', 'Own'];
  window.purchaseStatusRevision = 0;
  const recoveryKey = 'purchase-feedback-pending:' + pill.dataset.url;
  function rememberFeedback(pending) {
    try { if (pending) window.sessionStorage.setItem(recoveryKey, '1'); else window.sessionStorage.removeItem(recoveryKey); } catch (_) {}
  }
  const menu = document.createElement('div');
  menu.className = 'purchase-status-menu'; menu.hidden = true;
  menu.setAttribute('role', 'menu'); menu.setAttribute('aria-label', 'Purchase status');
  document.body.append(menu);

  function showMessage(text, feedback, failed = false) {
    if (!notice || !message) return;
    message.textContent = text;
    notice.hidden = !text;
    notice.classList.toggle('is-error', failed);
    if (feedbackLink) {
      const url = safeHandoff(feedback?.url);
      feedbackLink.hidden = !url;
      if (url) feedbackLink.href = url;
      else feedbackLink.removeAttribute('href');
    }
  }
  function safeHandoff(value) {
    if (!value) return null;
    try {
      const url = new URL(value, window.location.href);
      const expected = pill.dataset.url.replace(/\/purchase-status$/, '/feedback');
      return url.origin === window.location.origin && url.pathname === expected ? url.href : null;
    } catch (_) { return null; }
  }
  function closeMenu(focus = false) {
    menu.hidden = true; pill.setAttribute('aria-expanded', 'false');
    if (focus) pill.focus();
  }
  function placeMenu() {
    const rect = pill.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - menu.offsetHeight - 8)) + 'px';
  }
  function render(next) {
    if (!next || typeof next.status !== 'string') return;
    state = next;
    pill.textContent = state.label + ' ▾';
    pill.className = 'coin-lookup-btn status-flip-pill purchase-status-pill phase-' + state.status.toLowerCase();
    pill.disabled = busy || readOnly;
    pill.setAttribute('aria-busy', String(busy));
    pill.setAttribute('aria-label', 'Purchase status: ' + state.label + '. Change status');
    // Reflect delivery evidence without saving it as an owner override.
    if (!Array.from(select.options).some(o => o.value === state.value)) {
      const option = document.createElement('option'); option.value = state.value; option.textContent = state.label;
      select.append(option);
    }
    select.value = state.value;
    select.disabled = busy || readOnly;
    document.querySelectorAll('[data-sell-status-select]').forEach(other => { if (['Own', 'Sold'].includes(state.status)) other.value = state.status; });
    select.classList.toggle('status-ordered', phases.slice(0, 3).includes(state.status));
    Array.from(select.options).forEach(o => { if (o.value === 'Own') o.textContent = 'Owned — visually inspected'; });
    if (review) {
      review.hidden = !state.attention;
      review.title = state.review_reason || 'Review the purchase information';
    }
    menu.replaceChildren();
    const heading = document.createElement('p'); heading.textContent = 'Ordered → Shipped → Delivered → Owned';
    menu.append(heading);
    for (const status of phases) {
      const choice = document.createElement('button'); choice.type = 'button';
      choice.setAttribute('role', 'menuitemradio'); choice.setAttribute('aria-checked', String(status === state.status));
      choice.textContent = status === 'Own' ? 'Owned — visually inspected' : status;
      choice.dataset.purchasePhase = status; choice.disabled = status === state.status || busy;
      choice.addEventListener('click', () => changeStatus(status));
      menu.append(choice);
    }
    const more = document.createElement('button'); more.type = 'button'; more.textContent = 'Other statuses…';
    more.setAttribute('role', 'menuitem'); more.addEventListener('click', () => {closeMenu(); select.scrollIntoView({block: 'center'}); select.focus();});
    menu.append(more);
  }
  async function changeStatus(target) {
    if (busy || readOnly || !target || target === state.status) { render(state); closeMenu(); return; }
    const previous = state;
    const inspected = target === 'Own' && phases.slice(0, 3).includes(previous.status);
    let popup = null, uncertain = true;
    // Reserve a tab during the user's gesture; never open one for polling/no-op.
    if (inspected && pill.dataset.category === 'banknotes') {
      rememberFeedback(true);
      try {
        popup = window.open('about:blank', '_blank');
        if (popup) { popup.opener = null; popup.document.title = 'Preparing eBay feedback'; popup.document.body.textContent = 'Saving inspection and preparing seller feedback…'; }
      } catch (_) { popup = null; }
    }
    busy = true; window.purchaseStatusRevision += 1; closeMenu(); render(state); showMessage('');
    try {
      const lifecycleTarget = phases.includes(target);
      const url = lifecycleTarget ? pill.dataset.url : pill.dataset.url.replace(/\/purchase-status$/, '/save-field');
      const response = await fetch(url, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'}, signal: AbortSignal.timeout(15000),
        body: JSON.stringify({status: target, field: 'status', value: target, expected_status: previous.status,
          inspected, csrf_token: pill.dataset.csrf}),
      });
      const data = await response.json().catch(() => ({}));
      // A successful response with an unreadable body may follow a committed save.
      uncertain = response.ok || response.status >= 500 || data.lifecycle?.status === 'Own';
      if (!response.ok || !data.ok || !data.lifecycle) {
        if (data.lifecycle) state = data.lifecycle;
        throw new Error(data.error || 'Status could not be saved. Please try again.');
      }
      window.purchaseStatusRevision += 1;
      render(data.lifecycle);
      // Notify dependent display panels without invoking a second autosave.
      select.dispatchEvent(new CustomEvent('purchase-status-saved', {bubbles: true, detail: data.lifecycle}));
      document.dispatchEvent(new CustomEvent('purchase-sources-updated'));
      const feedback = data.feedback, handoff = safeHandoff(feedback?.url);
      rememberFeedback(false);
      if (feedback?.state === 'ready' && handoff) {
        if (popup && !popup.closed) popup.location.replace(handoff);
        showMessage('Owned saved. Seller feedback is ready: Positive, 5 stars, and your comment.', feedback);
      } else {
        popup?.close();
        if (inspected && feedback?.state === 'unavailable') showMessage('Owned saved. ' + feedback.message);
      }
    } catch (error) {
      popup?.close();
      if (!uncertain) rememberFeedback(false);
      const recovery = inspected && pill.dataset.category === 'banknotes' && uncertain
        ? {url: pill.dataset.url.replace(/\/purchase-status$/, '/feedback')} : null;
      showMessage((error.message || 'Could not confirm the save. Reload the record before retrying.') +
        (recovery ? ' If Owned was saved, use Open eBay feedback to continue.' : ''), recovery, true);
    } finally {
      busy = false; render(state);
    }
  }
  pill.addEventListener('click', () => {
    if (busy || readOnly) return;
    if (!menu.hidden) {closeMenu(); return;}
    menu.hidden = false; pill.setAttribute('aria-expanded', 'true'); placeMenu();
    menu.querySelector('button:not(:disabled)')?.focus();
  });
  menu.addEventListener('keydown', event => {
    if (event.key === 'Escape') {event.preventDefault(); closeMenu(true); return;}
    if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const buttons = Array.from(menu.querySelectorAll('button:not(:disabled)'));
    const index = buttons.indexOf(document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
      : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
    buttons[next]?.focus();
  });
  document.addEventListener('click', event => {if (!menu.contains(event.target) && !pill.contains(event.target)) closeMenu();});
  window.addEventListener('resize', () => {if (!menu.hidden) placeMenu();});
  window.addEventListener('scroll', () => {if (!menu.hidden) placeMenu();}, true);
  select.addEventListener('change', event => {event.stopImmediatePropagation(); changeStatus(select.value);}, true);
  document.addEventListener('purchase-lifecycle-updated', event => {
    const data = event.detail?.lifecycle || event.detail;
    const revision = event.detail?.revision;
    if (!busy && (revision == null || revision === window.purchaseStatusRevision)) render(data);
  });
  notice?.querySelector('[data-purchase-status-dismiss]')?.addEventListener('click', () => {notice.hidden = true;});
  render(state);
  try {
    if (state.status === 'Own' && window.sessionStorage.getItem(recoveryKey)) {
      showMessage('Owned is saved. Continue the seller feedback started after your inspection.',
        {url: pill.dataset.url.replace(/\/purchase-status$/, '/feedback')});
    }
  } catch (_) {}
})();
