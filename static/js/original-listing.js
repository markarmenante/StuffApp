(() => {
  const panel = document.querySelector('[data-original-listing]');
  if (!panel) return;
  const title = panel.querySelector('[data-listing-title]');
  const links = panel.querySelector('[data-purchase-links]');
  const reasons = panel.querySelector('[data-listing-reasons]');
  const progress = panel.querySelector('[data-listing-progress]');
  const error = panel.querySelector('[data-listing-error]');
  const button = panel.querySelector('[data-listing-action]');
  const deliveryBadge = document.querySelector('[data-delivery-badge]');
  const statusSelect = document.querySelector('#mainForm select[name="status"]');
  let result = JSON.parse(panel.querySelector('[data-listing-initial]').textContent);
  let attempts = 0, busy = false, timer;

  function renderDelivery(delivery) {
    if (!deliveryBadge || !delivery) return;
    const ownership = (statusSelect?.value || deliveryBadge.dataset.ownershipStatus || 'Own').trim().toLowerCase();
    const duplicate = delivery.status.toLowerCase() === ownership ||
      (delivery.status === 'Delivered' && ['own', 'owned'].includes(ownership));
    deliveryBadge.hidden = duplicate && !delivery.attention;
    deliveryBadge.textContent = duplicate && delivery.attention ? 'Please Review'
      : delivery.status + (delivery.attention ? ' \u00b7 Review' : '');
    deliveryBadge.className = duplicate && delivery.attention ? 'purchase-review-pill'
      : 'ebay-delivery-badge ebay-' + delivery.status.toLowerCase();
  }
  statusSelect?.addEventListener('change', () => renderDelivery(result.delivery));

  function render(data) {
    result = data;
    if (data.csrf_token) panel.dataset.csrf = data.csrf_token;
    const review = data.review, check = data.check;
    const differences = check?.differences || [];
    const needsReview = (review && !review.dismissed) || (differences.length > 0 && !check.dismissed);
    const reviewed = !needsReview && (review?.dismissed || check?.dismissed);
    renderDelivery(data.delivery);
    panel.hidden = !(data.links?.length || review || check);
    title.textContent = needsReview ? 'Review Reason' : reviewed ? 'Marked reviewed' : 'Purchase sources';
    links.replaceChildren();
    for (const source of data.links || []) {
      const link = document.createElement('a');
      link.className = 'purchase-review-source';
      link.href = source.url;
      link.textContent = source.label;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      links.append(link);
    }
    reasons.replaceChildren();
    if (review && !review.dismissed) {
      const evidence = document.createElement('nav');
      evidence.className = 'purchase-review-sources'; evidence.setAttribute('aria-label', 'Review sources');
      for (const source of review.sources || []) {
        if ((data.links || []).some(link => link.url === source.url)) continue;
        const link = document.createElement('a');
        link.className = 'purchase-review-source'; link.href = source.url;
        link.textContent = source.label; link.target = '_blank'; link.rel = 'noopener noreferrer';
        evidence.append(link);
      }
      reasons.append(evidence);
      const text = document.createElement('textarea');
      text.id = 'coinReviewReason'; text.rows = 3; text.readOnly = true; text.value = review.reason;
      reasons.append(text);
    }
    if (check && !check.dismissed) {
      for (const item of differences) {
        const line = document.createElement('p');
        line.className = 'listing-review-change';
        const description = document.createElement('span');
        const label = document.createElement('strong'); label.textContent = item.label + ': ';
        description.append(label, `${item.stored || 'Missing'}; ${item.source_label || 'listing'}: ${item.listed}`);
        line.append(description);
        line.title = item.evidence;
        if (button) {
          const actions = document.createElement('span');
          actions.className = 'listing-change-actions';
          for (const action of ['update', 'dismiss']) {
            const control = document.createElement('button');
            control.type = 'button'; control.className = 'purchase-review-action';
            control.textContent = action === 'update' ? 'Update' : 'Dismiss';
            control.dataset.field = item.field; control.dataset.changeAction = action;
            control.disabled = busy || (action === 'update' && item.update_value == null);
            control.title = action === 'update' ? (item.update_value == null ? 'Edit this ambiguous value manually'
              : `Update ${item.label} to ${item.update_value}`) : `Dismiss ${item.label} without changing the record`;
            control.setAttribute('aria-label', `${control.textContent} ${item.label}`);
            actions.append(control);
          }
          line.append(actions);
        }
        reasons.append(line);
      }
    }
    reasons.hidden = !needsReview;
    if (button) {
      button.hidden = !(needsReview || reviewed);
      button.textContent = needsReview ? 'Mark Reviewed' : 'Undo';
      button.dataset.listingAction = needsReview ? 'dismiss' : 'restore';
    }
    progress.textContent = check?.state === 'checked'
      ? `Listing checked: ${check.compared} field${check.compared === 1 ? '' : 's'} compared${differences.length ? '' : '; no differences found'}.`
      : check?.state === 'pending' ? 'Checking original listing...'
      : check?.state === 'failed' ? 'Listing comparison could not be completed.' : '';
    progress.hidden = !progress.textContent;
    const priceStatus = panel.querySelector('[data-listing-price]');
    priceStatus.textContent = check?.state === 'checked' ? (check.price?.outcome === 'match'
      ? `Purchase price verified: ${check.price.listed} (${check.price.source_label}).`
      : check.price ? '' : 'Purchase price has not been verified against an order or invoice.') : '';
    priceStatus.hidden = !priceStatus.textContent;
  }

  async function refresh() {
    if (busy) return;
    try {
      const response = await fetch(panel.dataset.url, {
        credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(10000),
      });
      if (!response.ok || busy) return;
      const data = await response.json();
      if (busy) return;
      render(data);
      if ((data.pending || data.archive_pending || data.check?.state === 'pending') && ++attempts < 40) {
        timer = window.setTimeout(refresh, 5000);
      }
    } catch (_) { /* A background check must not interrupt editing. */ }
  }
  async function submitAction(action, field) {
    if (busy) return;
    busy = true; button.disabled = true; error.hidden = true; clearTimeout(timer);
    panel.querySelectorAll('[data-change-action]').forEach(control => { control.disabled = true; });
    try {
      const body = new URLSearchParams({ action, csrf_token: panel.dataset.csrf,
        review_token: result.review?.token || '', check_token: result.check?.token || '' });
      if (field) body.set('field', field);
      const updating = field && action === 'update';
      const submit = () => fetch(updating ? panel.dataset.updateUrl : panel.dataset.url + '/review', {
        method: 'POST', credentials: 'same-origin', signal: AbortSignal.timeout(15000),
        headers: updating ? {'Content-Type': 'application/json'} : {},
        body: updating ? JSON.stringify({field, listing_check_token: body.get('check_token'),
          csrf_token: body.get('csrf_token')}) : body,
      });
      let response = await submit();
      let data = await response.json().catch(() => ({}));
      if (response.status === 403 && data.code === 'csrf_expired') {
        const currentResponse = await fetch(panel.dataset.url, {
          credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(10000),
        });
        const current = await currentResponse.json().catch(() => ({}));
        if (!currentResponse.ok || !current.csrf_token) {
          throw new Error('Could not refresh the page session. Reload and try again.');
        }
        // Renew only the session token; never acknowledge evidence the user has not seen.
        if ((current.review?.token || '') !== body.get('review_token') ||
            (current.check?.token || '') !== body.get('check_token')) {
          render(current);
          throw new Error('The review changed. Check the updated details before confirming it.');
        }
        panel.dataset.csrf = current.csrf_token;
        body.set('csrf_token', current.csrf_token);
        response = await submit();
        data = await response.json().catch(() => ({}));
      }
      if (!response.ok) throw new Error(data.error || 'Could not confirm the review. Reload and try again.');
      if (updating) {
        for (const [name, value] of Object.entries(data.updated_fields || {})) {
          const text = ['date_1', 'date_2'].includes(name) && Number(value) < 0
            ? `${Math.abs(Number(value))} BC` : String(value ?? '');
          document.querySelectorAll(`#mainForm [name="${CSS.escape(name)}"]`).forEach(input => {
            input.value = text;
          });
        }
        if (Object.prototype.hasOwnProperty.call(data, 'provenance_purchase')) {
          document.dispatchEvent(new CustomEvent('record-purchase-saved', {
            detail: {purchase: data.provenance_purchase, updatedAt: data.purchase_updated_at},
          }));
        }
      }
      render(updating ? data.listing : data);
    } catch (err) {
      error.textContent = err.message || 'Could not confirm the review.';
      error.hidden = false;
    } finally {
      busy = false; button.disabled = false; render(result);
    }
  }
  button?.addEventListener('click', () => submitAction(button.dataset.listingAction));
  reasons.addEventListener('click', event => {
    const control = event.target.closest('[data-change-action]');
    if (control && !control.disabled) submitAction(control.dataset.changeAction, control.dataset.field);
  });
  render(result);
  document.addEventListener('purchase-sources-updated', () => { attempts = 0; clearTimeout(timer); refresh(); });
  refresh();
})();
