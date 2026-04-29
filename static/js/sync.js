// StuffFiles round-trip sync — uses the File System Access API to
// extract the export zip directly into a folder the user picks once
// (handle persisted in IndexedDB), and to walk that same folder
// later to upload new files.
//
// Browser support: Chromium-based (Chrome, Edge, Brave, Comet, Arc).
// Safari/iOS/Firefox: NOT supported — caller should fall back to the
// existing blob-download path. Detect via window.showDirectoryPicker.
//
// Depends on JSZip (loaded via CDN in base.html) for unzipping the
// server response in the browser.

(function () {
  const DB_NAME  = 'stuffapp-sync';
  const STORE    = 'handles';
  const KEY      = 'StuffFilesDir';

  // IndexedDB for two things: persisted FileSystemDirectoryHandle, and
  // a per-path fingerprint map ({path: 'size:mtime'}) so re-runs of
  // syncUp can skip files that haven't changed since last upload.
  const STATE_KEY = 'StuffFilesSyncState';

  function _openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror   = () => reject(req.error);
    });
  }

  async function _loadSyncState() {
    const db = await _openDB();
    return new Promise((resolve) => {
      const tx  = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).get(STATE_KEY);
      req.onsuccess = () => resolve(req.result || {});
      req.onerror   = () => resolve({});
    });
  }

  async function _saveSyncState(state) {
    const db = await _openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(state, STATE_KEY);
      tx.oncomplete = () => resolve();
      tx.onerror    = () => reject(tx.error);
    });
  }

  // Public: forget what's been uploaded so the next syncUp re-uploads
  // everything (server still skips populated slots — this is a client-
  // side cache reset only).
  async function resetSyncState() {
    await _saveSyncState({});
  }

  async function _saveHandle(handle) {
    const db = await _openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(handle, KEY);
      tx.oncomplete = () => resolve();
      tx.onerror    = () => reject(tx.error);
    });
  }

  async function _loadHandle() {
    const db = await _openDB();
    return new Promise((resolve) => {
      const tx  = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).get(KEY);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror   = () => resolve(null);
    });
  }

  async function _getOrPickDirectory(forcePrompt) {
    let h = forcePrompt ? null : await _loadHandle();
    if (h) {
      let perm = await h.queryPermission({mode: 'readwrite'});
      if (perm !== 'granted') {
        try {
          perm = await h.requestPermission({mode: 'readwrite'});
        } catch (_) { perm = 'denied'; }
      }
      if (perm === 'granted') return h;
    }
    h = await window.showDirectoryPicker({
      mode: 'readwrite',
      id:   'stufffiles',
      startIn: 'documents',
    });
    await _saveHandle(h);
    return h;
  }

  async function _ensurePath(rootHandle, relPath) {
    const parts = relPath.split('/').filter(Boolean);
    let cur = rootHandle;
    for (let i = 0; i < parts.length - 1; i++) {
      cur = await cur.getDirectoryHandle(parts[i], {create: true});
    }
    return [cur, parts[parts.length - 1]];
  }

  // Public: pop the picker even if a handle is already saved (so the
  // user can re-target after moving folders).
  async function pickFolder() {
    return await _getOrPickDirectory(true);
  }

  // Public: download the export zip and extract it into the saved
  // (or freshly picked) StuffFiles folder. Calls progress(msg) at
  // milestones so the caller can update UI.
  async function syncDown(progress) {
    if (!window.showDirectoryPicker) {
      throw new Error('Browser does not support the directory picker; falling back to zip download.');
    }
    if (typeof JSZip === 'undefined') {
      throw new Error('JSZip not loaded.');
    }
    const dir = await _getOrPickDirectory(false);

    progress && progress('Building zip on server (can take a minute)…');
    const r = await fetch('/export-files');
    if (!r.ok) throw new Error('Server returned HTTP ' + r.status);
    const blob = await r.blob();
    const sizeMB = (blob.size / 1024 / 1024).toFixed(1);
    progress && progress(`Extracting ${sizeMB} MB into your folder…`);

    const zip = await JSZip.loadAsync(blob);
    const entries = [];
    zip.forEach((relPath, entry) => {
      if (!entry.dir) entries.push([relPath, entry]);
    });
    let done = 0;
    let written = 0;
    for (const [name, entry] of entries) {
      // Strip the "StuffFiles/" prefix — the user already picked the
      // StuffFiles directory, so the zip's contents land relative to it.
      const rel = name.replace(/^StuffFiles\//, '');
      if (!rel) continue;
      try {
        const [parent, fname] = await _ensurePath(dir, rel);
        const file = await parent.getFileHandle(fname, {create: true});
        const writer = await file.createWritable();
        const data = await entry.async('uint8array');
        await writer.write(data);
        await writer.close();
        written++;
      } catch (e) {
        // Best-effort: skip a file we can't write rather than aborting
        // the whole sync. Surface the count at the end.
        console.warn('Skipped', rel, e);
      }
      done++;
      if (done % 10 === 0 || done === entries.length) {
        progress && progress(`Wrote ${written}/${entries.length} files…`);
      }
    }
    return {written, total: entries.length};
  }

  // Read a single iCloud-aware file. macOS keeps iCloud Drive files as
  // on-disk stubs until accessed; the first .arrayBuffer() call
  // triggers the download which can take seconds. Retry with backoff
  // on transient failures or 0-byte reads.
  async function _readWithIcloudRetry(handle, progress) {
    let lastErr;
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const file = await handle.getFile();
        const buf = await file.arrayBuffer();
        if (buf.byteLength === 0 && file.size > 0) {
          throw new Error('iCloud-stub: 0 bytes read, size says ' + file.size);
        }
        return new File([buf], handle.name, {type: file.type || ''});
      } catch (e) {
        lastErr = e;
        if (attempt < 3) {
          progress && progress(`Waiting on iCloud for ${handle.name}… (try ${attempt + 2}/4)`);
          await new Promise(r => setTimeout(r, 1500 * (attempt + 1)));
        }
      }
    }
    throw lastErr;
  }

  // POST one batch of files to /sweep with a retry on transient
  // network failure. Returns parsed JSON or throws with the last
  // error.
  async function _uploadBatch(files, autoCreate) {
    const fd = new FormData();
    if (autoCreate) fd.append('auto_create', '1');
    for (const f of files) fd.append('files', f, f.name);
    let lastErr;
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const r = await fetch('/sweep', {
          method: 'POST',
          headers: {'Accept': 'application/json'},
          body: fd,
          credentials: 'include',
        });
        if (!r.ok) throw new Error('Server returned HTTP ' + r.status);
        return await r.json();
      } catch (e) {
        lastErr = e;
        if (attempt === 0) await new Promise(r => setTimeout(r, 1500));
      }
    }
    throw lastErr;
  }

  // Public: walk the saved folder, upload every file inside via /sweep.
  // Reads files one at a time so iCloud-stub files have a chance to
  // download, then uploads in batches so a single POST doesn't exceed
  // Cloudflare's body limit or the server's request timeout.
  // Idempotent — server skips slots that already have a file, so
  // re-runs only land genuinely new local files.
  async function syncUp(progress) {
    if (!window.showDirectoryPicker) {
      throw new Error('Browser does not support the directory picker.');
    }
    const BATCH_FILES = 20;
    const BATCH_BYTES = 25 * 1024 * 1024;  // 25 MB per POST max
    const dir = await _getOrPickDirectory(false);

    const handles = [];
    async function walk(handle, prefix) {
      for await (const [name, child] of handle.entries()) {
        if (name.startsWith('.')) continue;
        if (child.kind === 'file') {
          handles.push({path: prefix + name, handle: child});
        } else if (child.kind === 'directory') {
          await walk(child, prefix + name + '/');
        }
      }
    }
    progress && progress('Walking your folder…');
    await walk(dir, 'StuffFiles/');
    if (!handles.length) return {uploaded: [], skipped: [], note: 'Folder is empty.'};

    // Diff against last sync's per-file fingerprints so we only read +
    // upload files that are new or changed since last time. Cheap —
    // just calls getFile() to read size/lastModified, which doesn't
    // pull file content from iCloud.
    const lastState = await _loadSyncState();
    const newState = {};
    const changed = [];
    for (const h of handles) {
      try {
        const meta = await h.handle.getFile();
        const fp = `${meta.size}:${meta.lastModified}`;
        newState[h.path] = fp;
        if (lastState[h.path] !== fp) changed.push(h);
      } catch (_) {
        // If metadata can't be read, force-include and let the read
        // step decide if the file is reachable.
        changed.push(h);
      }
    }
    if (!changed.length) {
      // Persist the fresh state too — even unchanged files; doesn't
      // hurt and keeps the cache aligned with reality.
      await _saveSyncState(newState);
      return {uploaded: [], skipped: [], note: `No new or changed files (scanned ${handles.length}).`};
    }
    progress && progress(`Scanned ${handles.length}; ${changed.length} new/changed. Uploading…`);

    const uploaded = [];
    const skipped  = [];
    let batch = [];
    let batchSize = 0;
    let done = 0;

    async function flush() {
      if (!batch.length) return;
      progress && progress(`Sending batch of ${batch.length} (${done}/${handles.length} read)…`);
      try {
        const data = await _uploadBatch(batch, true);
        if (data.uploaded) uploaded.push(...data.uploaded);
        if (data.skipped) {
          skipped.push(...data.skipped);
          // Per-file server errors (try/except path on the server) are
          // transient — drop them from newState so the next syncUp retries.
          // Deterministic skips (slot-full, no-record-match, …) stay in
          // newState so we don't keep re-uploading the same junk.
          for (const s of data.skipped) {
            if (typeof s.reason === 'string' && s.reason.startsWith('server error:')) {
              delete newState[s.file];
            }
          }
        }
      } catch (e) {
        for (const f of batch) {
          skipped.push({file: f.name, reason: 'batch upload failed: ' + (e.message || e)});
          // Whole batch lost — leave entries out of newState so they
          // retry next run. f.name === h.path because we wrap with
          // `new File([tmp], h.path, …)` above.
          delete newState[f.name];
        }
      }
      batch = [];
      batchSize = 0;
    }

    for (let i = 0; i < changed.length; i++) {
      const h = changed[i];
      progress && progress(`Reading ${i + 1}/${changed.length}: ${h.path.split('/').pop()}`);
      let wrapped;
      try {
        const tmp = await _readWithIcloudRetry(h.handle, progress);
        wrapped = new File([tmp], h.path, {type: tmp.type || ''});
      } catch (e) {
        skipped.push({file: h.path, reason: 'read failed (iCloud not downloaded yet?): ' + (e.message || e)});
        done++;
        // Don't promote this file in newState — leave it for next run.
        delete newState[h.path];
        continue;
      }
      batch.push(wrapped);
      batchSize += wrapped.size;
      done++;
      if (batch.length >= BATCH_FILES || batchSize >= BATCH_BYTES) {
        await flush();
      }
    }
    await flush();

    // Persist the new fingerprint map. Files that succeeded (or were
    // skipped server-side because the slot was full — same outcome
    // either way) won't be re-uploaded next run. Files that errored
    // mid-read had their entry deleted above so they retry next run.
    await _saveSyncState(newState);
    return {uploaded, skipped, scanned: handles.length, changed: changed.length};
  }

  window.StuffSync = {syncDown, syncUp, pickFolder, resetSyncState};
})();
