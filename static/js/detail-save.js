/* Keep native form saves from re-reading already uploaded or missing local files. */
(function () {
  'use strict';
  const form = document.getElementById('mainForm');
  if (!form) return;
  const pending = new Set();
  const snapshot = () => [...form.querySelectorAll('input[type=file]')]
    .map(input => ({input, files: [...input.files]})).filter(entry => entry.files.length);
  const sameFiles = ({input, files}) => input.files.length === files.length
    && files.every((file, index) => input.files[index] === file);
  const clear = (entries, acknowledged) => entries.forEach(entry => {
    if ((!acknowledged || acknowledged.includes(entry.input.name)) && sameFiles(entry)) entry.input.value = '';
  });
  function track(promise) {
    const completion = Promise.resolve(promise).then(() => true, () => false);
    pending.add(completion);
    completion.then(() => pending.delete(completion));
    return promise;
  }
  const uploadQueues = new WeakMap();
  function upload(target, operation) {
    // Selecting another photo while the first is saving must leave the newer
    // photo last on the server as well as in the picker.
    const previous = uploadQueues.get(target) || Promise.resolve();
    const promise = previous.catch(() => {}).then(operation);
    uploadQueues.set(target, promise);
    promise.then(() => { if (uploadQueues.get(target) === promise) uploadQueues.delete(target); },
      () => { if (uploadQueues.get(target) === promise) uploadQueues.delete(target); });
    return track(promise);
  }
  window.detailSave = {snapshot, clear, track, upload};
  let preparing = false, ready = false;
  let notice;
  function showError(message) {
    if (!notice) {
      notice = document.createElement('p'); notice.setAttribute('role', 'alert');
      notice.dataset.detailSaveError = '';
      notice.style.cssText = 'position:sticky;bottom:0;padding:12px;background:#fff4e5;color:#833d00;border:1px solid #e5b66e;z-index:20';
      form.append(notice);
    }
    notice.textContent = message; notice.hidden = false;
    notice.scrollIntoView({block: 'nearest'});
  }
  form.addEventListener('submit', event => {
    if (ready) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (preparing || form.inert) return;
    preparing = true;
    window.__stuffAllowUnload = false;
    if (notice) notice.hidden = true;
    const submitter = event.submitter;
    (async () => {
      while (pending.size) {
        if ((await Promise.all([...pending])).some(ok => !ok)) {
          throw new Error('A file could not be saved. Your edits are still here. Retry the upload before saving.');
        }
      }
      if (window.waitForCheckSaves) await window.waitForCheckSaves();
      // A disk-backed File can disappear after a screenshot or download is
      // moved. Read pending files before navigation and submit memory copies.
      // Preserve newer selections made while these reads are in flight.
      let entries;
      do {
        entries = snapshot();
        const copies = await Promise.all(entries.map(async entry => {
          const files = await Promise.all(entry.files.map(async file => {
            let bytes;
            try { bytes = await file.arrayBuffer(); }
            catch (_) { throw new Error(`“${file.name}” is no longer available. Choose that file again. Your other edits are still here.`); }
            return new File([bytes], file.name, {type: file.type, lastModified: file.lastModified});
          }));
          return {entry, files};
        }));
        const current = snapshot();
        if (current.length !== entries.length || entries.some((entry, index) =>
            current[index]?.input !== entry.input || !sameFiles(entry)) || pending.size) {
          while (pending.size) {
            if ((await Promise.all([...pending])).some(ok => !ok)) throw new Error('A file could not be saved. Retry its upload before saving.');
          }
          continue;
        }
        copies.forEach(({entry, files}) => {
          const transfer = new DataTransfer(); files.forEach(file => transfer.items.add(file));
          entry.input.files = transfer.files;
        });
        break;
      } while (true);
      ready = true;
      try { form.requestSubmit(submitter?.isConnected ? submitter : undefined); }
      finally { ready = false; }
    })().catch(error => { window.__stuffAllowUnload = false; showError(error.message || 'Save did not finish. Your edits are still here.'); })
      .finally(() => { preparing = false; });
  }, true);
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      if (!event.repeat && !form.inert) form.requestSubmit();
    }
  });
})();
