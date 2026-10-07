(() => {
  const panel = document.querySelector('[data-original-listing]');
  if (!panel) return;
  const title = panel.querySelector('[data-listing-title]');
  const links = panel.querySelector('[data-purchase-links]');
  const reasons = panel.querySelector('[data-listing-reasons]');
  const progress = panel.querySelector('[data-listing-progress]');
  const error = panel.querySelector('[data-listing-error]');
  const button = panel.querySelector('[data-listing-action]');
  let result = JSON.parse(panel.querySelector('[data-listing-initial]').textContent);
  let attempts = 0, busy = false, timer;

  function render(data) {
    result = data;
    const review = data.review, check = data.check;
    const differences = check?.differences || [];
    const needsReview = (review && !review.dismissed) || (differences.length > 0 && !check.dismissed);
    const reviewed = !needsReview && (review?.dismissed || check?.dismissed);
    const deliveryBadge = document.querySelector('[data-delivery-badge]');
    if (deliveryBadge && data.delivery) {
      deliveryBadge.textContent = data.delivery.status + (data.delivery.attention ? ' \u00b7 Review' : '');
      deliveryBadge.className = 'ebay-delivery-badge ebay-' + data.delivery.status.toLowerCase();
    }
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
        const label = document.createElement('strong'); label.textContent = item.label + ': ';
        line.append(label, `${item.stored || 'Missing'}; listing: ${item.listed}`);
        line.title = item.evidence;
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
  button?.addEventListener('click', async () => {
    if (busy) return;
    busy = true; button.disabled = true; error.hidden = true; clearTimeout(timer);
    try {
      const response = await fetch(panel.dataset.url + '/review', {
        method: 'POST', credentials: 'same-origin', signal: AbortSignal.timeout(15000),
        body: new URLSearchParams({ action: button.dataset.listingAction, csrf_token: panel.dataset.csrf,
          review_token: result.review?.token || '', check_token: result.check?.token || '' }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Could not confirm the review. Reload and try again.');
      render(data);
    } catch (err) {
      error.textContent = err.message || 'Could not confirm the review.';
      error.hidden = false;
    } finally {
      busy = false; button.disabled = false;
    }
  });
  render(result);
  refresh();
})();
