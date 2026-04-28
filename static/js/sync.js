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

  function _openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror   = () => reject(req.error);
    });
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

  // Public: walk the saved folder, upload every file inside via /sweep.
  // Server-side /sweep skips slots that are already populated, so this
  // is idempotent — re-runs only land genuinely new files.
  async function syncUp(progress) {
    if (!window.showDirectoryPicker) {
      throw new Error('Browser does not support the directory picker.');
    }
    const dir = await _getOrPickDirectory(false);
    const files = [];
    async function walk(handle, prefix) {
      for await (const [name, child] of handle.entries()) {
        if (name.startsWith('.')) continue;
        if (child.kind === 'file') {
          files.push({path: prefix + name, handle: child});
        } else if (child.kind === 'directory') {
          await walk(child, prefix + name + '/');
        }
      }
    }
    progress && progress('Walking your folder…');
    await walk(dir, 'StuffFiles/');
    if (!files.length) return {uploaded: [], skipped: [], note: 'Folder is empty.'};
    progress && progress(`Found ${files.length} files. Uploading…`);

    const fd = new FormData();
    fd.append('auto_create', '1');
    for (const f of files) {
      const file = await f.handle.getFile();
      // Re-wrap the File so its name carries the full relative path
      // (server's _parse_sweep_path keys off this).
      fd.append('files', new File([file], f.path, {type: file.type || ''}));
    }
    progress && progress('Sending to server (this is the slow part)…');
    const r = await fetch('/sweep', {
      method: 'POST',
      headers: {'Accept': 'application/json'},
      body: fd,
    });
    if (!r.ok) throw new Error('Server returned HTTP ' + r.status);
    return await r.json();
  }

  window.StuffSync = {syncDown, syncUp, pickFolder};
})();
