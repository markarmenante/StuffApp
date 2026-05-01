// StuffFiles round-trip sync — uses the File System Access API to
// extract the export zip directly into a folder the user picks once
// (handle persisted in IndexedDB), and to walk that same folder
// later to upload new files.
//
// Browser support: Chromium-based (Chrome, Edge, Brave, Comet, Arc).
// Safari/iOS/Firefox: NOT supported — caller should fall back to the
// existing blob-download path. Detect via window.showDirectoryPicker.
//
// Depends on fflate (loaded via CDN in base.html) for streaming
// unzip — the response body is piped chunk-by-chunk through
// fflate.Unzip and each decompressed file is written straight to
// disk via FileSystemWritableFileStream. JSZip's loadAsync() pulled
// the whole zip into RAM via FileReader and OOM-crashed Chrome on
// multi-GB exports.

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
  //
  // After writing the zip's contents, runs a purge pass: walks the
  // directories the export wrote into and prompts the user to delete
  // any local file whose path isn't in the new export. Catches
  // renamed-away leftovers (e.g. cat_id "CA001 …" when the new
  // scheme wrote "C001 …" — the rename produces a duplicate-looking
  // pair without the purge). Skipped on dotfiles and on subtrees the
  // export didn't touch, so the user's private subdirs are safe.
  async function syncDown(progress) {
    if (!window.showDirectoryPicker) {
      throw new Error('Browser does not support the directory picker; falling back to zip download.');
    }
    if (typeof fflate === 'undefined') {
      throw new Error('fflate not loaded.');
    }
    const dir = await _getOrPickDirectory(false);

    progress && progress('Building zip on server (can take a minute)…');
    const r = await fetch('/export-files');
    if (!r.ok) throw new Error('Server returned HTTP ' + r.status);
    if (!r.body) throw new Error('Streaming response body not supported.');
    progress && progress('Streaming export into your folder…');

    // Track every path the export wrote so the purge pass below can
    // diff against what's currently on disk. `expectedPaths` is the
    // set of file paths relative to the picked StuffFiles dir, and
    // `managedTopLevel` is the set of first-segment dirs the export
    // claims (Coins / Properties / Watches / …). Once we're inside
    // any of those, every subdir is app-managed and a candidate for
    // purge — that's how a renamed-away record's folder (the property
    // formerly known as "4956 Fifth") finally gets cleaned up even
    // though no zip entry pulled the walker into it.
    const expectedPaths = new Set();
    const managedTopLevel = new Set();

    // Unicode normalization fix: macOS stores filenames in NFD
    // (decomposed — "ö" is "o" + combining "¨"), while the zip and
    // the rest of our world ship NFC ("ö" as a single code point).
    // Without normalizing on the comparison side, every brand with a
    // diacritic (A. Lange & Söhne, Jules Jürgensen, …) gets flagged
    // as stale even though the on-disk file is the SAME file. We
    // normalize both ends to NFC before insertion / lookup.
    const NFC = (s) => s.normalize('NFC');

    // Outer try/catch: from this point on, ANY uncaught error gets
    // captured and surfaced as a partial-success result instead of
    // bubbling up as a "Sync failed" rejection. We've already pulled
    // the zip down successfully — there's no value in throwing away
    // the writes that did land just because one read mid-walk hit a
    // transient iCloud-stub or revoked-permission glitch.
    let syncError = null;
    let written = 0;
    let total = 0;
    let purged = 0;
    let purgedDirs = 0;
    let staleCount = 0;
    try {
    // Stream the response body through fflate.Unzip — chunks of the
    // zip flow in, decompressed file chunks come out via onfile/ondata
    // and get written straight to disk. Strips the leading
    // "StuffFiles/" prefix because the user already picked that dir.
    const unzipper = new fflate.Unzip();
    unzipper.register(fflate.UnzipInflate);

    // All disk writes funnel through one chained promise so the read
    // loop can apply backpressure (await it between input chunks).
    // Without this, fflate buffers decompressed chunks faster than
    // the disk consumes them and we recreate the OOM.
    let writeChain = Promise.resolve();

    unzipper.onfile = (file) => {
      // Directory entries arrive with a trailing slash and no data;
      // _ensurePath creates intermediate dirs lazily so we skip these.
      if (file.name.endsWith('/')) return;
      const rel = NFC(file.name.replace(/^StuffFiles\//, ''));
      if (!rel) return;
      expectedPaths.add(rel);
      const top = rel.split('/')[0];
      if (top) managedTopLevel.add(top);
      total++;

      let writer = null;
      let aborted = false;

      file.ondata = (err, data, final) => {
        writeChain = writeChain.then(async () => {
          if (aborted) return;
          try {
            if (err) throw err;
            if (!writer) {
              const [parent, fname] = await _ensurePath(dir, rel);
              const fileHandle = await parent.getFileHandle(fname, {create: true});
              writer = await fileHandle.createWritable();
            }
            if (data && data.length) await writer.write(data);
            if (final) {
              await writer.close();
              written++;
              if (written % 10 === 0) {
                progress && progress(`Wrote ${written} files…`);
              }
            }
          } catch (e) {
            // Best-effort: skip a file we can't write rather than
            // aborting the whole sync. Surface the count at the end.
            aborted = true;
            console.warn('Skipped', rel, e);
            if (writer) {
              try { await writer.abort(); } catch (_) {}
            }
          }
        });
      };

      file.start();
    };

    const reader = r.body.getReader();
    let bytesIn = 0;
    let lastProgressBytes = 0;
    while (true) {
      const {done: rDone, value} = await reader.read();
      if (rDone) {
        unzipper.push(new Uint8Array(0), true);
        break;
      }
      unzipper.push(value, false);
      bytesIn += value.length;
      if (bytesIn - lastProgressBytes > 50 * 1024 * 1024) {
        const sizeMB = (bytesIn / 1024 / 1024).toFixed(0);
        progress && progress(`Extracting (${sizeMB} MB read, ${written} files written)…`);
        lastProgressBytes = bytesIn;
      }
      // Backpressure: drain the write queue before the next read so
      // we cap RAM at roughly one input chunk plus its expansion.
      await writeChain;
    }
    await writeChain;
    progress && progress(`Wrote ${written}/${total} files…`);

    // Purge pass: walk every subtree under a managed top-level dir
    // (Coins, Properties, …) and collect files that aren't in the
    // new export. Once we're inside a managed subtree, recurse all
    // the way down — that catches a renamed-away record's folder
    // even though no zip entry pulled the walker into it. Dirs at
    // the StuffFiles root that aren't ours stay untouched.
    progress && progress('Checking for stale files…');
    const stale = [];
    let scanErrors = 0;
    async function findStale(parentHandle, prefix, inManaged) {
      // Each iteration is wrapped in try/catch so a single entry that
      // can't be read (typically an iCloud stub or a permission glitch
      // on one file) doesn't abort the whole purge walk and bubble up
      // as "Sync failed: file could not be read".
      try {
        for await (const [name, child] of parentHandle.entries()) {
          try {
            if (name.startsWith('.')) continue;  // dotfiles are user-owned
            // Compare in NFC so umlauts / accents on disk (NFD) match
            // the composed form in expectedPaths (NFC). The on-disk
            // `name` is kept as-is for the eventual removeEntry() call.
            const normName = NFC(name);
            const path = prefix ? `${prefix}/${normName}` : normName;
            if (child.kind === 'file') {
              if (inManaged && !expectedPaths.has(path)) {
                stale.push({path, parent: parentHandle, name});
              }
            } else if (child.kind === 'directory') {
              // Top-level dirs only count as managed if the export
              // wrote into them this run. Below the top level, every
              // subdir is app-territory and gets recursed.
              const childManaged = inManaged || managedTopLevel.has(normName);
              if (childManaged) {
                await findStale(child, path, true);
              }
            }
          } catch (e) {
            scanErrors++;
            console.warn('[StuffSync] skip entry', prefix + '/' + name, e);
          }
        }
      } catch (e) {
        scanErrors++;
        console.warn('[StuffSync] iterator failed at', prefix || '<root>', e);
      }
    }
    await findStale(dir, '', false);
    if (scanErrors) {
      console.warn(`[StuffSync] purge scan completed with ${scanErrors} entry-level error(s)`);
    }
    console.log('[StuffSync] purge scan',
      'managed top-level:', [...managedTopLevel],
      'expected files:', expectedPaths.size,
      'stale found:', stale.length,
      stale.length ? '(first 5 paths: ' + stale.slice(0, 5).map(s => s.path).join(' | ') + ')' : '');

    staleCount = stale.length;
    if (stale.length > 0) {
      const sample = stale.slice(0, 12).map(s => s.path).join('\n');
      const more = stale.length > 12 ? `\n…and ${stale.length - 12} more` : '';
      const ok = window.confirm(
        `Delete ${stale.length} stale file(s) from your StuffFiles folder?\n\n` +
        `These files exist locally but aren't in the latest export — usually ` +
        `because the underlying record was renamed (e.g. cat_id changed) and ` +
        `the new file already landed under the new name. Empty directories ` +
        `left behind will be removed too.\n\n` +
        sample + more
      );
      if (ok) {
        for (const s of stale) {
          try {
            await s.parent.removeEntry(s.name);
            purged++;
          } catch (e) {
            console.warn('Failed to purge', s.path, e);
          }
        }
        // Second pass: walk managed subtrees again and remove any
        // directory that's now empty. Goes depth-first so the deepest
        // empty dirs go before their (newly-empty) parents.
        async function pruneEmpty(parentHandle, prefix, inManaged) {
          // Same per-entry resilience as findStale: one bad entry
          // shouldn't abort the whole prune.
          const dirsHere = [];
          try {
            for await (const [name, child] of parentHandle.entries()) {
              try {
                if (name.startsWith('.')) continue;
                if (child.kind !== 'directory') continue;
                const normName = NFC(name);
                const path = prefix ? `${prefix}/${normName}` : normName;
                const childManaged = inManaged || managedTopLevel.has(normName);
                if (!childManaged) continue;
                await pruneEmpty(child, path, true);
                dirsHere.push({name, normName, child, path});
              } catch (e) {
                console.warn('[StuffSync] skip prune entry',
                             prefix + '/' + name, e);
              }
            }
          } catch (e) {
            console.warn('[StuffSync] prune iterator failed at',
                         prefix || '<root>', e);
          }
          for (const {name, normName, child, path} of dirsHere) {
            try {
              // Don't blow away a top-level managed dir even if empty —
              // re-creating it on the next sync just hits the same
              // permission prompts. Only prune below the top level.
              if (managedTopLevel.has(normName) && !inManaged) continue;
              let isEmpty = true;
              for await (const _entry of child.entries()) {  // eslint-disable-line no-unused-vars
                isEmpty = false; break;
              }
              if (!isEmpty) continue;
              await parentHandle.removeEntry(name);
              purgedDirs++;
            } catch (e) {
              console.warn('Failed to remove empty dir', path, e);
            }
          }
        }
        try {
          await pruneEmpty(dir, '', false);
        } catch (e) {
          console.warn('Empty-dir prune failed:', e);
        }
      }
    }

    } catch (e) {
      // Anything that escaped the per-step try/catches lands here. We
      // hold onto the message and keep returning whatever progress we
      // already made — the caller surfaces it as a warning suffix on
      // the success toast instead of clobbering the result.
      syncError = e && (e.message || String(e));
      console.warn('[StuffSync] uncaught syncDown error:', e);
    }

    return {written, total,
            stale: staleCount, purged, purgedDirs,
            error: syncError};
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
