(() => {
  'use strict';
  const panel = document.getElementById('banknoteEconomics');
  if (!panel) return;
  const amount = panel.querySelector('[data-economic="at_issue_display"]');
  const relevant = new Set(['country', 'issuer', 'denomination', 'series', 'date_1', 'date_1_text', 'issue_date', 'issue_type']);
  let timer, generation = 0;
  async function refresh() {
    if (!panel.dataset.url) return;
    const request = ++generation;
    try {
      const response = await fetch(panel.dataset.url, {headers: {'Accept': 'application/json'}, cache: 'no-store'});
      if (!response.ok) throw new Error('Economic data could not be refreshed.');
      const data = await response.json();
      if (request !== generation) return;
      amount.textContent = data.at_issue_display || 'Unavailable';
      amount.title = [`Series year: ${data.comparison_year || 'Unknown'}.`,
        data.estimate_basis, data.comparison_basis, data.at_issue == null ? data.note : '']
        .filter(Boolean).join(' ');
    } catch {
      // Retain the last calculation when shared public data cannot be refreshed.
    }
  }
  function schedule(field) {
    if (!relevant.has(field)) return;
    clearTimeout(timer);
    timer = setTimeout(refresh, 250);
  }
  document.addEventListener('record-field-saved', event => schedule(event.detail?.field));
  document.addEventListener('change', event => {
    if (event.detail?.lookupApplied) schedule(event.target.name);
  });
  refresh();
})();
