/* Saved banknote order drafts: collection writes require explicit Release. */
(() => {
  'use strict';
  const sameOrigin = value => {
    const url = new URL(value, window.location.href);
    if (url.origin !== window.location.origin || !['http:', 'https:'].includes(url.protocol)) {
      throw new Error('The saved order returned an invalid link.');
    }
    return url.pathname + url.search + url.hash;
  };
  const webLink = value => {
    try { const url = new URL(value, window.location.href); return ['https:', 'http:'].includes(url.protocol) ? url.href : ''; }
    catch (_) { return ''; }
  };
  async function request(url, method = 'GET', body) {
    const response = await fetch(sameOrigin(url), {
      method, credentials: 'same-origin', cache: 'no-store',
      headers: {Accept: 'application/json', ...(body ? {'Content-Type': 'application/json'} : {})},
      ...(body ? {body: JSON.stringify(body)} : {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.error) {
      const error = new Error(data.error || (response.status === 401 || response.status === 403
        ? 'Sign in again to continue. Your saved drafts are kept.' : 'Could not save this change. Please try again.'));
      error.status = response.status; error.data = data; throw error;
    }
    return data;
  }
  window.startBanknoteOrderReview = async function (orderNumber, options = {}) {
    const value = String(orderNumber || '').trim();
    if (!value) throw new Error('Enter the eBay order number first.');
    const data = await request('/banknotes/imports', 'POST', {order_number: value, ...(options.refresh === true ? {refresh:true} : {})});
    if (!data.url) throw new Error('The order was saved but its review link was missing. Open Order review to resume.');
    return {...data, url: sameOrigin(data.url)};
  };
  const root = document.querySelector('[data-import-mode]');
  if (!root) return;
  const mode = root.dataset.importMode;
  const status = document.getElementById('banknoteImportStatus');
  const say = (message, error = false) => {
    status.textContent = message || ''; status.dataset.error = String(error);
  };
  const text = value => value === null || value === undefined ? '' : String(value);
  const el = (tag, value, className) => {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = value;
    if (className) node.className = className;
    return node;
  };
  if (mode === 'new') {
    document.getElementById('banknoteImportOrderForm').addEventListener('submit', async event => {
      event.preventDefault();
      const button = document.getElementById('banknoteImportStart');
      if (button.disabled) return;
      button.disabled = true; say('Saving order for review…');
      try {
        const batch = await window.startBanknoteOrderReview(document.getElementById('banknoteImportOrderNumber').value);
        window.location.assign(batch.url);
      } catch (error) { say(error.message, true); button.disabled = false; }
    });
    return;
  }
  const seed = JSON.parse(document.getElementById('banknote-import-data').textContent);
  let batch = seed.batch;
  let item = seed.item;
  const batchUrl = '/banknotes/imports/' + encodeURIComponent(batch.id);
  const statusUrl = sameOrigin(batch.status_url || batchUrl + '/status');
  const refresh = document.getElementById('banknoteImportRefresh');
  let pollTimer, pollFailures = 0, polling = false;
  let form, fields = [], baseline = {}, saving = null, saveTimer, busy = false, busyAction = '', conflict = null;
  let leftPage = false;
  const dirty = () => fields.some(field => field.value !== (baseline[field.name] || ''));
  // The shared detail form displays units/currency, while saved draft fields
  // retain their canonical values. Compare display to display for CAS merges.
  function displayValue(field, data) {
    const value = text(data?.[field.name]);
    if (!root.classList.contains('banknote-import-detail')) return value;
    if (field.name === 'date_1') return text(data?.date_1_text) || (/^-\d+$/.test(value) ? value.slice(1) + ' BC' : value);
    if (!value) return value;
    if (field.name === 'price' && /^-?\d+(?:\.\d+)?$/.test(value)) {
      const parts = value.split('.');
      return '$' + parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + (parts[1] || '').padEnd(2,'0');
    }
    if (field.classList.contains('coin-unit-input')) return value + (field.dataset.suffix || '');
    return value;
  }
  function assignField(field, value) {
    if (field.tagName === 'SELECT' && value && ![...field.options].some(option => option.value === value)) {
      field.add(new Option(value === 'Own' ? 'Owned' : value, value));
    }
    field.value = value;
  }
  function syncDetailDisplay() {
    if (!form || !root.classList.contains('banknote-import-detail')) return;
    form.querySelectorAll('.date-overlay-input').forEach(input => {
      const display = input.parentElement.querySelector('.date-overlay-display');
      if (display) display.textContent = /^\d{4}-\d{2}-\d{2}$/.test(input.value)
        ? input.value.slice(5,7) + '/' + input.value.slice(8,10) + '/' + input.value.slice(0,4) : input.value;
    });
    form.querySelectorAll('[data-md-preview-for]').forEach(preview => {
      const field = form.elements.namedItem(preview.dataset.mdPreviewFor);
      if (!field) return;
      if (preview.dataset.savedText !== field.value) { preview.innerHTML = window.formatResultsHtml(field.value); preview.dataset.savedText = field.value; }
      if (!field.value) { preview.style.display = 'none'; field.style.display = ''; }
    });
    fields.filter(field => field.tagName === 'TEXTAREA').forEach(field => window._autosizeTextarea?.(field));
    const grade = form.elements.namedItem('grade');
    const summary = form.querySelector('.banknote-grade-summary');
    if (summary) summary.value = [grade?.selectedOptions[0]?.textContent || '', form.elements.namedItem('grade_modifier')?.value || ''].filter(Boolean).join(' ');
    form.querySelectorAll('.banknote-imgs .coin-img-panel[data-field]').forEach(panel => {
      const filename = item.fields?.[panel.dataset.field];
      const img = panel.querySelector('img');
      if (!filename) { img?.remove(); panel.querySelector('.quad-fix-btn')?.remove(); return; }
      const url = sameOrigin(root.dataset.uploadedFileTemplate.replace('__draft_image__', encodeURIComponent(filename)));
      const image = img || el('img');
      if (image.getAttribute('src') !== url) image.src = url;
      image.alt = panel.dataset.field === 'image_1' ? 'Banknote front' : 'Banknote back';
      panel.querySelector(':scope > span')?.remove();
      if (!img) panel.prepend(image);
      window.ensureBanknoteCropControl?.(panel);
    });
  }
  const checkRunning = draft => draft.check_state === 'checking';
  const batchRunning = () => ['queued', 'sign_in_required', 'challenge_required'].includes(batch.state)
    || (batch.items || []).some(draft => draft.state === 'draft' && ['idle', 'checking'].includes(draft.check_state));
  const stateLabel = draft => draft.state === 'released' ? 'In collection' : draft.state === 'blocked'
    ? 'Needs attention' : checkRunning(draft) ? 'Checking…' : draft.check_state === 'failed'
    ? 'Check needs retry' : draft.check_state === 'partial' ? 'Review needed' : 'Saved draft';
  function appendPhoto(parent, photo, index, detailUrl, large = false) {
    let src; try { src = sameOrigin(photo.url); } catch (_) { return; }
    const anchor = el('a'); anchor.href = large ? src : sameOrigin(detailUrl);
    if (large) { anchor.target = '_blank'; anchor.rel = 'noopener'; }
    const image = el('img'); image.src = src; image.alt = 'Purchased banknote photo ' + (index + 1);
    image.loading = index < 2 ? 'eager' : 'lazy'; anchor.append(image);
    if (large) {
      const figure = el('figure'); figure.dataset.photoFilename = photo.filename || ''; figure.tabIndex = -1;
      const caption = el('figcaption', 'Photo ' + (index + 1));
      for (const [field, label] of [['image_1','Front'], ['image_2','Back']]) {
        const badge = el('span', label, 'import-badge'); badge.dataset.photoSelected = field; badge.hidden = true; caption.append(badge);
      }
      figure.append(anchor, caption);
      if (photo.filename && photo.selectable !== false) {
        const actions = el('div', undefined, 'import-photo-actions');
        for (const [field, label] of [['image_1','front'], ['image_2','back']]) {
          const button = el('button', 'Use as ' + label, 'toolbar-btn pill');
          button.type = 'button'; button.dataset.photoSide = field; button.dataset.photoFilename = photo.filename;
          button.setAttribute('aria-label', 'Use photo ' + (index + 1) + ' as ' + label);
          button.addEventListener('click', () => selectPhoto(photo, field)); actions.append(button);
        }
        figure.append(actions);
      }
      parent.append(figure);
    }
    else parent.append(anchor);
  }
  const missing = draft => [['country','country'],['denomination','denomination'],['pick_number','catalogue number']]
    .filter(([name]) => !text(draft.fields?.[name]).trim()).map(([,label]) => label);
  function renderList() {
    const list = document.getElementById('banknoteImportList');
    const fragment = document.createDocumentFragment();
    (batch.items || []).forEach(draft => {
      const card = el('article', undefined, 'import-card'); card.dataset.draftId = draft.id;
      const photos = el('div', undefined, 'import-card-photos');
      const originals = draft.photos || [];
      const previews = ['image_1','image_2'].map((field, index) => {
        const filename = draft.fields?.[field];
        return filename ? originals.find(photo => photo.filename === filename)
          || {filename, url:'/uploads/' + encodeURIComponent(filename)} : originals[index];
      }).filter(Boolean);
      previews.forEach((photo, index) => appendPhoto(photos, photo, index, draft.detail_url));
      if (!photos.children.length) photos.append(el('span', checkRunning(draft) ? 'Loading purchased photos…' : 'Photos not yet available', 'import-photo-empty'));
      const body = el('div');
      body.append(el('h2', draft.title || [draft.fields?.country, draft.fields?.denomination].filter(Boolean).join(' · ') || 'Purchased banknote'));
      const identity = ['country','denomination','date_1_text','pick_number','grading_authority','grade_numeric','grade_modifier']
        .map(name => text(draft.fields?.[name])).filter(Boolean).join(' · ');
      if (identity) body.append(el('p', identity));
      const price = text(draft.fields?.price);
      body.append(el('p', [price ? 'Item price: ' + price : 'Item price not available', draft.fields?.vendor ? 'Seller: ' + draft.fields.vendor : '', 'Order: ' + draft.order_number].filter(Boolean).join(' · ')));
      const absent = missing(draft);
      if (absent.length && draft.state !== 'released') body.append(el('p', 'Missing: ' + absent.join(', ')));
      const actions = el('div', undefined, 'import-actions');
      const review = el('a', draft.state === 'released' ? 'View reviewed item' : 'Review details', 'toolbar-btn pill active');
      review.href = sameOrigin(draft.detail_url); review.dataset.reviewDraft = draft.id;
      actions.append(review, el('span', stateLabel(draft), 'import-badge'));
      if (draft.existing_record_id) {
        const existing = el('a', 'Completes existing record', 'import-badge');
        existing.href = '/banknotes/' + encodeURIComponent(draft.existing_record_id);
        existing.target = '_blank'; existing.rel = 'noopener'; actions.append(existing);
      }
      if (draft.listing_url && webLink(draft.listing_url)) {
        const listing = el('a', 'View listing', 'toolbar-btn pill'); listing.href = webLink(draft.listing_url);
        listing.target = '_blank'; listing.rel = 'noopener noreferrer'; actions.append(listing);
      }
      body.append(actions); card.append(photos, body); fragment.append(card);
    });
    // Do not steal keyboard focus during a background Check update.
    const focused = document.activeElement?.dataset.reviewDraft;
    list.replaceChildren(fragment);
    if (focused) [...list.querySelectorAll('[data-review-draft]')].find(link => link.dataset.reviewDraft === focused)?.focus({preventScroll:true});
    document.getElementById('banknoteImportCount').textContent = batch.pending_count + ' pending';
    say(batch.message || (batch.state === 'queued' ? 'Retrieving the purchased items…'
      : batch.pending_count ? 'Drafts saved. Review each item before releasing it.' : 'All reviewed items are in the collection.'));
    document.getElementById('banknoteImportRetry').hidden = batch.state !== 'failed';
    document.getElementById('banknoteImportRefreshOrder').disabled = ['queued','sign_in_required','challenge_required'].includes(batch.state);
  }
  function evidenceText(value) {
    if (typeof value === 'string') return value;
    return value?.message || value?.warning || value?.summary || value?.title || value?.label || value?.field || '';
  }
  const existingChanges = () => item?.existing_record_changes || [];
  const draftConflict = error => error.status === 409 && (error.data?.code === 'draft_changed'
    || (!error.data?.code && /(?:draft.*changed|newer draft revision|draft revision.*changed)/i.test(error.message)));
  function actionError(error, suffix = '') {
    if (error.data?.code === 'existing_record_changed' && error.data.item) setRemote(error.data.item);
    else if (draftConflict(error)) {
      conflict = {pending:true}; refresh.hidden = false; refresh.textContent = 'Review latest saved values';
    }
    say(error.message + suffix, true);
    renderDetail();
  }
  function renderExistingChanges() {
    const panel = document.getElementById('banknoteImportExistingChanges');
    if (!panel) return;
    const changes = existingChanges();
    panel.hidden = !changes.length || item.state !== 'draft';
    if (panel.hidden) return;
    const comparison = document.getElementById('banknoteImportExistingComparison');
    const compared = changes.map(change => ({...change, draft: fields.find(field => field.name === change.field)?.value ?? item.fields?.[change.field]}));
    const signature = JSON.stringify(compared);
    if (comparison.dataset.changes !== signature) {
      comparison.dataset.changes = signature; comparison.replaceChildren();
      compared.forEach(change => {
        const name = change.field;
        const field = fields.find(candidate => candidate.name === name);
        const label = name === 'image_1' ? 'Front photo' : name === 'image_2' ? 'Back photo'
          : field?.closest('.dcell, .bottom-cell')?.querySelector('.clabel, .blabel')?.textContent || name.replaceAll('_',' ');
        const section = el('div', undefined, 'import-existing-change');
        section.append(el('strong', label));
        const values = el('div', undefined, 'import-existing-values');
        [['draft','Current draft'],['current','Current collection record']].forEach(([key, title]) => {
          const value = text(change[key]); const figure = el('figure');
          figure.append(el('figcaption', title));
          if (value && (name === 'image_1' || name === 'image_2')) {
            const url = sameOrigin(root.dataset.uploadedFileTemplate.replace('__draft_image__', encodeURIComponent(value)));
            const link = el('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener';
            const image = el('img'); image.src = url; image.alt = title + ' — ' + label; link.append(image); figure.append(link);
          } else figure.append(el('p', value || '(blank)'));
          values.append(figure);
        });
        section.append(values); comparison.append(section);
      });
    }
    const update = document.getElementById('banknoteImportRefreshExisting');
    // A blur-triggered autosave must not disable the button between pointerdown
    // and click. Its handler awaits any in-flight save before refreshing.
    update.disabled = busy || checkRunning(item) || Boolean(conflict);
    update.textContent = busyAction === 'refresh-existing' ? 'Updating draft…' : 'Update draft from collection';
    const link = document.getElementById('banknoteImportExistingLink');
    link.href = sameOrigin(item.existing_record_url || '/banknotes/' + encodeURIComponent(item.existing_record_id));
  }
  function renderDetail() {
    syncDetailDisplay();
    renderExistingChanges();
    form?.setAttribute('aria-busy', String(busy || Boolean(saving)));
    document.getElementById('banknoteImportState').textContent = stateLabel(item);
    const gallery = document.getElementById('banknoteImportPhotos');
    const signature = JSON.stringify(item.photos || []);
    if (gallery.dataset.photos !== signature) {
      gallery.dataset.photos = signature; gallery.replaceChildren();
      (item.photos || []).forEach((photo, index) => appendPhoto(gallery, photo, index, item.detail_url, true));
      if (!gallery.children.length) gallery.append(el('p', checkRunning(item) ? 'Loading purchased photos…' : 'No purchased photos available yet. Use Check to retry.'));
    }
    const warnings = document.getElementById('banknoteImportWarnings');
    warnings.replaceChildren(); warnings.hidden = !(item.warnings || []).length;
    if (!warnings.hidden) {
      warnings.append(el('strong', 'Needs review')); const list = el('ul');
      item.warnings.forEach(warning => list.append(el('li', evidenceText(warning)))); warnings.append(list);
    }
    const evidence = document.getElementById('banknoteImportEvidence');
    evidence.hidden = !(item.evidence || []).length; const entries = evidence.querySelector('ul'); entries.replaceChildren();
    (item.evidence || []).forEach(source => {
      const li = el('li'); const href = webLink(typeof source === 'object' ? source.url || source.source_url || '' : '');
      if (href && typeof source === 'object' && (source.url || source.source_url)) {
        const a = el('a', evidenceText(source) || 'Source'); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; li.append(a);
      } else li.textContent = evidenceText(source);
      entries.append(li);
    });
    const editable = item.state === 'draft';
    form?.querySelectorAll('.quad-fix-btn').forEach(button => {
      button.hidden = !editable;
      button.disabled = !editable || busy || checkRunning(item) || Boolean(conflict);
    });
    const openCollection = document.getElementById('banknoteImportOpenCollection');
    if (openCollection) {
      openCollection.hidden = item.state !== 'released' || !item.released_record_id;
      if (!openCollection.hidden) openCollection.href = '/banknotes/' + encodeURIComponent(item.released_record_id);
    }
    const imageHelp = document.getElementById('banknoteImportImageHelp');
    if (imageHelp) {
      imageHelp.replaceChildren();
      if (item.state === 'released' && item.released_record_id) {
        const link = el('a', 'Edit photos in collection');
        link.href = '/banknotes/' + encodeURIComponent(item.released_record_id); imageHelp.append(link);
      } else {
        imageHelp.textContent = item.fields?.image_1 || item.fields?.image_2
          ? 'Use ✂ on either photo to adjust its crop. Changes stay in this draft until release.'
          : 'Choose front and back from Purchased photos below, then use ✂ to adjust each crop.';
      }
    }
    const preserved = new Set(item.preserved_fields || []);
    gallery.querySelectorAll('figure[data-photo-filename]').forEach(figure => {
      const filename = figure.dataset.photoFilename;
      figure.querySelectorAll('[data-photo-selected]').forEach(badge => {
        const field = badge.dataset.photoSelected;
        badge.hidden = !filename || (item.fields?.[field] !== filename && item.image_sources?.[field] !== filename);
      });
      const actions = figure.querySelector('.import-photo-actions');
      if (actions) actions.hidden = !editable;
      figure.querySelectorAll('[data-photo-side]').forEach(button => {
        const field = button.dataset.photoSide;
        const oppositeField = field === 'image_1' ? 'image_2' : 'image_1';
        const selected = item.fields?.[field] === filename || item.image_sources?.[field] === filename;
        const opposite = item.fields?.[oppositeField] === filename || item.image_sources?.[oppositeField] === filename;
        button.disabled = !editable || busy || checkRunning(item) || Boolean(conflict) || preserved.has(field) || selected || opposite;
        button.setAttribute('aria-pressed', String(selected));
        button.title = preserved.has(field) ? 'The existing record’s photo is preserved.' : selected
          ? 'Selected for this side.' : opposite ? 'This photo is already selected for the other side.' : '';
      });
    });
    fields.forEach(field => {
      field.readOnly = preserved.has(field.name);
      field.disabled = !editable || busy || (field.tagName === 'SELECT' && preserved.has(field.name));
    });
    document.getElementById('banknoteImportSave').disabled = !editable || busy || Boolean(saving);
    const check = document.getElementById('banknoteImportCheck');
    check.disabled = !editable || busy || checkRunning(item) || Boolean(conflict);
    check.textContent = checkRunning(item) ? 'Checking…' : item.check_state === 'failed' ? 'Retry Check' : '✓ Check';
    const release = document.getElementById('banknoteImportRelease');
    release.disabled = !editable || busy || checkRunning(item) || Boolean(conflict) || Boolean(existingChanges().length);
    release.textContent = busyAction === 'release' ? 'Releasing…' : 'Release to Collection';
    release.title = existingChanges().length ? 'Review the collection changes and update this draft first.' : '';
  }
  function setRemote(remote) {
    if (saving) return false;
    // A status request can finish after a newer autosave response.
    if (Number(remote.revision) < Number(item.revision)) return false;
    const conflicting = fields.filter(field => field.value !== baseline[field.name]
      && displayValue(field, remote.fields) !== baseline[field.name]
      && displayValue(field, remote.fields) !== field.value);
    if (conflicting.length) {
      conflict = remote;
      say('This draft changed elsewhere. Your edits are kept here. Review the saved values before saving again.', true);
      refresh.hidden = false; refresh.textContent = 'Review latest saved values'; renderDetail(); return false;
    }
    fields.forEach(field => {
      const value = displayValue(field, remote.fields);
      if (field.value === baseline[field.name]) assignField(field, value);
      baseline[field.name] = value;
    });
    item = remote; renderDetail(); return true;
  }
  async function saveDraft() {
    clearTimeout(saveTimer);
    if (conflict) throw new Error('This draft changed elsewhere. Review the latest saved values first. Your edits are still here.');
    if (saving) { await saving; if (dirty()) return saveDraft(); return; }
    if (!dirty()) return;
    if (item.state !== 'draft') throw new Error('This item is no longer an editable draft. Your edits have not been released.');
    const updates = {};
    fields.forEach(field => { if (field.value !== baseline[field.name]) updates[field.name] = field.value; });
    say('Saving draft…');
    saving = (async () => {
      try {
        const result = await request(item.detail_url, 'POST', {revision:item.revision, updates});
        const remote = result.item;
        if (!remote) throw new Error('The draft save could not be confirmed. Your edits are kept here.');
        fields.forEach(field => {
          const oldValue = baseline[field.name];
          if (Object.hasOwn(updates, field.name)) {
            // Only reflect canonical saved values if typing has not continued.
            if (field.value === updates[field.name]) assignField(field, displayValue(field, remote.fields));
          } else if (field.value === oldValue) assignField(field, displayValue(field, remote.fields));
          baseline[field.name] = displayValue(field, remote.fields);
        });
        item = remote; say(dirty() ? 'Saving your latest edits…' : 'Draft saved · not yet in collection');
      } catch (error) {
        actionError(error, ' Your edits are kept here.');
        throw error;
      }
    })();
    renderDetail();
    try { await saving; } finally { saving = null; renderDetail(); }
    if (dirty()) await saveDraft();
  }
  async function selectPhoto(photo, field) {
    if (busy || conflict || checkRunning(item) || item.state !== 'draft' || photo.selectable === false
        || (item.preserved_fields || []).includes(field)) return;
    busy = true; renderDetail();
    try {
      await saveDraft();
      say('Saving the ' + (field === 'image_1' ? 'front' : 'back') + ' photo…');
      const result = await request(item.detail_url + '/photos', 'POST', {revision:item.revision, field, filename:photo.filename});
      if (!result.item) throw new Error('The photo choice could not be confirmed. Refresh the saved status before trying again.');
      if (setRemote(result.item)) say('Photo choice saved · not yet in collection');
    } catch (error) {
      actionError(error);
    } finally { busy = false; renderDetail(); }
  }
  // The familiar crop editor delegates only its persistence for saved drafts.
  // Hold the draft stable while it is open; bind Save to the revision and photo
  // that supplied the visible corners, never a later background response.
  window.banknoteImportCrop = {
    async load(field) {
      if (busy || conflict || checkRunning(item) || item.state !== 'draft') {
        throw new Error('Finish the current draft action before editing this photo.');
      }
      busy = true; busyAction = 'crop'; renderDetail();
      try {
        await saveDraft();
        return await request(item.detail_url + '/trim-quad/' + encodeURIComponent(field));
      } catch (error) { actionError(error); throw error; }
    },
    async save(field, info, quad) {
      try {
        const result = await request(item.detail_url + '/trim-quad/' + encodeURIComponent(field), 'POST', {
          revision:info.revision, trimmed:info.trimmed, quad,
        });
        if (!result.item) throw new Error('The crop save could not be confirmed. Refresh the saved status before trying again.');
        if (setRemote(result.item)) say('Crop saved · not yet in collection');
        return result;
      } catch (error) { actionError(error); throw error; }
    },
    close() {
      if (busyAction !== 'crop') return;
      busy = false; busyAction = ''; renderDetail();
    },
  };
  function showConflict(remote) {
    document.getElementById('banknoteImportConflict')?.remove();
    const panel = el('section', undefined, 'import-evidence'); panel.id = 'banknoteImportConflict';
    panel.append(el('strong', 'A newer draft was saved'));
    const list = el('ul');
    fields.filter(field => field.value !== displayValue(field, remote.fields)).forEach(field => {
      const label = field.closest('label')?.querySelector('span')?.textContent || field.closest('.dcell, .bottom-cell')?.querySelector('.clabel, .blabel')?.textContent || field.name;
      list.append(el('li', label + ' — saved: ' + (displayValue(field, remote.fields) || '(blank)') + ' · your edit: ' + (field.value || '(blank)')));
    });
    panel.append(list); const actions = el('div', undefined, 'import-actions');
    const keep = el('button', 'Keep my edits', 'toolbar-btn pill active'); keep.type = 'button';
    const use = el('button', 'Use saved values', 'toolbar-btn pill'); use.type = 'button';
    keep.addEventListener('click', async () => {
      const localEdits = Object.fromEntries(fields.filter(field => field.value !== baseline[field.name]).map(field => [field.name,field.value]));
      fields.forEach(field => { baseline[field.name] = displayValue(field, remote.fields); assignField(field, Object.hasOwn(localEdits,field.name) ? localEdits[field.name] : baseline[field.name]); });
      item = remote; conflict = null; panel.remove(); refresh.hidden = true;
      try { await saveDraft(); } catch (_) {} renderDetail();
    });
    use.addEventListener('click', () => {
      fields.forEach(field => { baseline[field.name] = displayValue(field, remote.fields); assignField(field, baseline[field.name]); });
      item = remote; conflict = null; panel.remove(); refresh.hidden = true; say('Showing the latest saved draft.'); renderDetail();
    });
    actions.append(keep,use); panel.append(actions); status.after(panel);
  }
  async function pollStatus(manual = false) {
    if (polling || leftPage) return;
    polling = true;
    try {
      const next = await request(statusUrl); batch = next.batch || next; pollFailures = 0;
      if (mode === 'review') renderList();
      else {
        const remote = (batch.items || []).find(draft => String(draft.id) === String(item.id));
        if (remote) {
          if (manual && conflict) showConflict(remote);
          else if (!conflict && !busy && setRemote(remote) && !dirty() && !saving) {
            say(item.state === 'released' ? 'Released to collection.' : existingChanges().length
              ? 'The collection record changed. Review the updates below before releasing this draft.' : checkRunning(item)
              ? 'Draft saved. Checking photos and missing details…' : item.check_state === 'failed'
              ? 'Draft saved. Check did not finish; you can retry it.' : 'Draft saved · not yet in collection');
          }
        }
      }
      if (!conflict) { refresh.hidden = true; refresh.textContent = 'Refresh saved status'; }
    } catch (error) {
      pollFailures += 1;
      if (!dirty() && !saving) say('Could not refresh the saved order. ' + error.message, true);
      refresh.hidden = false;
    } finally {
      polling = false;
      const running = batchRunning() || Boolean(saving);
      if (running && pollFailures < 5 && !leftPage) { clearTimeout(pollTimer); pollTimer = setTimeout(() => pollStatus(), 2500); }
    }
  }
  refresh.addEventListener('click', () => pollStatus(true));
  if (mode === 'review') {
    renderList();
    const readOrder = async (event, forceRefresh) => {
      const button = event.currentTarget; button.disabled = true;
      try {
        say('Refreshing the exact purchased items. Saved draft edits are kept…');
        const saved = await window.startBanknoteOrderReview(batch.order_number, {refresh:forceRefresh});
        if (saved.url !== batchUrl) window.location.assign(saved.url); else await pollStatus(true);
      } catch (error) { say(error.message,true); }
      finally { button.disabled = button.id === 'banknoteImportRefreshOrder' && ['queued','sign_in_required','challenge_required'].includes(batch.state); }
    };
    document.getElementById('banknoteImportRetry').addEventListener('click', event => readOrder(event, false));
    document.getElementById('banknoteImportRefreshOrder').addEventListener('click', event => readOrder(event, true));
  } else {
    form = document.getElementById('mainForm') || document.getElementById('banknoteImportDetailForm');
    const allowed = new Set(seed.allowed_fields || [...form.querySelectorAll('[name]')].map(field => field.name));
    fields = [...form.querySelectorAll('input[name]:not([type=file]), textarea[name], select[name]')].filter(field => allowed.has(field.name));
    if (root.classList.contains('banknote-import-detail')) {
      form.querySelectorAll('[name]').forEach(field => {
        if (allowed.has(field.name)) assignField(field, displayValue(field, item.fields));
        else if (field.tagName === 'SELECT') field.disabled = true;
        else field.readOnly = true;
      });
      form.querySelectorAll('[data-md-preview-for]').forEach(preview => {
        const field = form.elements.namedItem(preview.dataset.mdPreviewFor);
        if (!field) return;
        preview.dataset.savedText = field.value;
        const edit = () => {
          if (field.disabled || field.readOnly) return;
          preview.style.display = 'none'; field.style.display = ''; field.focus(); window._autosizeTextarea?.(field);
        };
        preview.addEventListener('click', event => { if (!event.target.closest('a')) edit(); });
        preview.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); edit(); } });
        field.addEventListener('blur', () => {
          if (field.value) { preview.innerHTML = window.formatResultsHtml(field.value); preview.dataset.savedText = field.value; preview.style.display = ''; field.style.display = 'none'; }
        });
      });
      form.querySelectorAll('.coin-date-edit-btn').forEach(button => button.addEventListener('click', () => {
        const field = document.getElementById(button.dataset.target);
        if (field && !field.disabled && !field.readOnly) { field.focus(); field.select(); }
      }));
      form.querySelectorAll('.ta-input').forEach((input, index) => {
        const options = (input.dataset.ta || '').split('||').filter(Boolean);
        if (!options.length) return;
        const list = el('datalist'); list.id = 'draft-options-' + index;
        options.forEach(value => list.append(new Option(value, value)));
        input.setAttribute('list', list.id); input.after(list);
      });
      form.querySelectorAll('.banknote-imgs .coin-img-panel').forEach(panel => {
        panel.addEventListener('click', () => {
          const image = panel.querySelector('img');
          if (image?.getAttribute('src')) window.open(sameOrigin(image.getAttribute('src')), '_blank', 'noopener');
        });
      });
    }
    fields.forEach(field => {
      baseline[field.name] = field.value;
      field.addEventListener('input', () => {
        if (field.name === 'date_1') {
          const companion = fields.find(candidate => candidate.name === 'date_1_text');
          if (companion && !companion.readOnly && !companion.disabled) companion.value = field.value;
        }
        syncDetailDisplay(); renderExistingChanges();
        say('Unsaved changes…'); clearTimeout(saveTimer);
        if (!conflict) saveTimer = setTimeout(() => saveDraft().catch(() => {}), 650);
      });
      field.addEventListener('change', () => { if (!conflict) saveDraft().catch(() => {}); });
      field.addEventListener('blur', () => { if (!conflict) saveDraft().catch(() => {}); });
    });
    form.addEventListener('submit', event => { event.preventDefault(); saveDraft().catch(() => {}); });
    document.addEventListener('keydown', event => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault(); saveDraft().catch(() => {});
      }
    });
    document.getElementById('banknoteImportSave').addEventListener('click', () => saveDraft().catch(error => say(error.message,true)));
    document.getElementById('banknoteImportCheck').addEventListener('click', async () => {
      if (busy || checkRunning(item)) return;
      busy = true; renderDetail();
      try {
        await saveDraft();
        const result = await request(item.detail_url + '/check', 'POST', {revision:item.revision});
        if (result.item) item = result.item;
        say('Draft saved. Checking photos and missing details…');
        clearTimeout(pollTimer); pollTimer = setTimeout(() => pollStatus(), 1000);
      } catch (error) { actionError(error); }
      finally { busy = false; renderDetail(); }
    });
    document.getElementById('banknoteImportRefreshExisting')?.addEventListener('click', async () => {
      if (busy || checkRunning(item) || conflict || !existingChanges().length) return;
      // Bind the acknowledgement to the values the user actually reviewed, even
      // if saving local edits reveals a newer change in the collection.
      const reviewedVersion = item.existing_record_version;
      busy = true; busyAction = 'refresh-existing'; renderDetail();
      try {
        await saveDraft(); say('Updating the draft from the collection record…');
        const result = await request(item.detail_url + '/refresh-existing', 'POST', {revision:item.revision, existing_record_version:reviewedVersion});
        if (!result.item) throw new Error('The draft update could not be confirmed. Refresh the saved status before trying again.');
        if (setRemote(result.item)) say('Draft updated. Review the note, then click Release to Collection when ready.');
      } catch (error) { actionError(error); }
      finally { busy = false; busyAction = ''; renderDetail(); }
    });
    document.getElementById('banknoteImportRelease').addEventListener('click', async () => {
      if (busy || checkRunning(item)) return;
      busy = true; busyAction = 'release'; renderDetail();
      try {
        await saveDraft(); say('Releasing to collection…');
        const result = await request(batchUrl + '/release', 'POST', {items:[{id:item.id,revision:item.revision}]});
        if (!result.next_url) throw new Error('The release could not be confirmed. Refresh the saved status before trying again.');
        leftPage = true; window.location.assign(sameOrigin(result.next_url));
      } catch (error) {
        actionError(error);
      } finally { busy = false; busyAction = ''; renderDetail(); }
    });
    document.querySelectorAll('[data-import-back]').forEach(link => link.addEventListener('click', async event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      try { await saveDraft(); leftPage = true; window.location.assign(sameOrigin(link.href)); }
      catch (error) { say(error.message,true); }
    }));
    window.addEventListener('beforeunload', event => {
      if (!leftPage && (dirty() || saving)) { event.preventDefault(); event.returnValue = ''; }
    });
    renderDetail();
    if (item.state === 'released') say('Released to collection. Open in Collection to edit this note or its photos.');
  }
  if (batchRunning()) pollTimer = setTimeout(() => pollStatus(), 1200);
})();
