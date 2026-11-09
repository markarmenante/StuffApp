(() => {
  'use strict';
  const panel = document.getElementById('coinEconomics');
  if (!panel) return;
  const relevant = new Set(['region', 'mint', 'authority', 'denomination', 'metal', 'weight',
    'date_1', 'date_1_text', 'date_2', 'date_2_text', 'fineness', 'fineness_basis', 'fineness_source']);
  const identityFields = new Set(['region', 'mint', 'authority', 'denomination', 'metal',
    'date_1', 'date_1_text', 'date_2', 'date_2_text']);
  const changedIdentity = new Set();
  let generation = 0, timer, quoteTimer, editing = false;
  document.addEventListener('input', event => {
    if (identityFields.has(event.target.name) && !event.detail?.lookupApplied) changedIdentity.add(event.target.name);
  });
  panel.querySelectorAll('[data-fineness]').forEach(input => input.addEventListener('input', () => { editing = true; }));
  async function refresh() {
    if (!panel.dataset.url) return;
    const request = ++generation;
    try {
      const response = await fetch(panel.dataset.url, {headers: {'Accept': 'application/json'}, cache: 'no-store'});
      if (!response.ok) throw new Error('Refresh unavailable');
      const data = await response.json();
      if (request !== generation) return;
      panel.querySelectorAll('[data-coin-economic]').forEach(el => {
        const value = data[el.dataset.coinEconomic];
        if (value !== undefined) el.textContent = Array.isArray(value) ? value.join(' · ') : value ?? '';
      });
      const links = panel.querySelector('[data-coin-economic-sources]');
      links.replaceChildren();
      (data.sources || []).forEach(source => {
        let url;
        try { url = new URL(source.url); } catch { return; }
        if (url.protocol !== 'https:' || url.username || url.password) return;
        const link = document.createElement('a');
        link.href = url.href; link.textContent = source.name; link.target = '_blank'; link.rel = 'noopener noreferrer';
        links.appendChild(link);
      });
      if (!editing) {
        panel.dataset.finenessIdentity = data.fineness_identity;
        panel.dataset.finenessState = data.fineness_state;
        panel.querySelectorAll('[data-fineness]').forEach(input => {
          input.value = data['fineness_' + input.dataset.fineness] ?? '';
        });
      }
      clearTimeout(quoteTimer);
      if (data.quote_refreshing) quoteTimer = setTimeout(refresh, 2000);
    } catch {
      if (request === generation) panel.querySelector('[data-coin-economic="quote_status"]').textContent =
        'Refresh unavailable — displayed calculation and source dates retained';
    }
  }
  panel.querySelectorAll('[data-fineness-action]').forEach(button => button.addEventListener('click', async () => {
    const status = panel.querySelector('[data-fineness-status]');
    const buttons = panel.querySelectorAll('[data-fineness-action]');
    buttons.forEach(el => { el.disabled = true; });
    status.textContent = 'Saving…';
    try {
      // Land only the identity edits the user actually made, including a
      // cleared field. An older purity proposal must then fail its server guard.
      const edited = [...changedIdentity].map(name => [name, document.querySelector(`[name="${name}"]`)?.value]);
      await Promise.all(edited.map(async ([name, value]) => {
        const result = await window.saveField(name, value);
        if (!result?.ok) throw new Error('Save the coin details before recording fineness.');
      }));
      if (edited.some(([name, value]) => document.querySelector(`[name="${name}"]`)?.value !== value)) {
        throw new Error('The coin details changed. Review the source again before saving fineness.');
      }
      const body = {action: button.dataset.finenessAction, expected_identity: panel.dataset.finenessIdentity,
        expected_fineness: panel.dataset.finenessState};
      panel.querySelectorAll('[data-fineness]').forEach(input => { body[input.dataset.fineness] = input.value; });
      const response = await fetch(panel.dataset.finenessUrl, {method: 'POST',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'}, body: JSON.stringify(body)});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Fineness could not be saved.');
      if (data.proposal) {
        panel.dataset.finenessIdentity = data.proposal.fineness_identity;
        panel.querySelector('[data-fineness="percent"]').value = data.proposal.fineness * 100;
        panel.querySelector('[data-fineness="basis"]').value = data.proposal.fineness_basis;
        panel.querySelector('[data-fineness="source"]').value = data.proposal.fineness_source;
        editing = true;
        status.textContent = data.message;
        return;
      }
      editing = false;
      status.textContent = 'Fineness and provenance saved.';
      await refresh();
    } catch (error) { status.textContent = error.message || 'Fineness could not be saved.'; }
    finally { buttons.forEach(el => { el.disabled = false; }); }
  }));
  function schedule(field) {
    if (!relevant.has(field)) return;
    ++generation;
    clearTimeout(timer);
    timer = setTimeout(refresh, 250);
  }
  document.addEventListener('record-field-saved', event => schedule(event.detail?.field));
  document.addEventListener('change', event => {
    if (event.detail?.lookupApplied) schedule(event.target.name);
  });
  refresh();
  // One shared server-side refresh per ten minutes; display the fresh result
  // without making the page wait for the public provider on its first request.
  setInterval(() => { if (!document.hidden) refresh(); }, 600000);
})();
