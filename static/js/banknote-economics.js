(() => {
  'use strict';
  const panel = document.getElementById('banknoteEconomics');
  if (!panel) return;
  const input = panel.querySelector('[name="issue_date"]');
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
      panel.querySelector('[data-economic-comparison-label]').textContent = String(data.estimate_kind || '').startsWith('historical_')
        ? 'Series-year benchmark · today’s USD' : 'Buying power in series year · today’s USD';
      panel.querySelectorAll('[data-economic]').forEach(el => {
        const value = data[el.dataset.economic];
        if (value !== undefined) el.textContent = Array.isArray(value) ? value.join(' · ') : value || '';
      });
      if (input) input.placeholder = data.probable_issue_date;
      const links = panel.querySelector('[data-economic-sources]');
      links.replaceChildren();
      (data.sources || []).forEach(source => {
        const url = new URL(source.url);
        if (url.protocol !== 'https:' || url.username || url.password) return;
        const a = document.createElement('a');
        a.href = url.href; a.textContent = source.name; a.target = '_blank'; a.rel = 'noopener noreferrer';
        links.appendChild(a);
      });
    } catch {
      if (request === generation) panel.querySelector('[data-economic="note"]').textContent = 'Refresh unavailable; the displayed calculation and source dates were retained.';
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
