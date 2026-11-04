/* Read a requested eBay order through this computer's authorized browser.
 * The server owns purchase validation. Capabilities live only in this document;
 * reopening a page never recovers or silently repeats a claimed read.
 */
(() => {
  'use strict';
  const EXTENSION_ID = 'fneejjjbhjdbppmedabagldignnjpdek';
  const ENDPOINT = '/ebay/browser/requests';
  const SETUP_URL = '/ebay/browser/setup';
  const jobs = new Map();
  const activeStates = new Set(['queued', 'reading', 'sign_in_required', 'challenge_required']);
  const messages = {
    reading: 'Reading this exact eBay order on this computer…',
    sign_in_required: 'Sign in to eBay in the opened tab. This order will resume here.',
    challenge_required: 'Complete eBay verification in the opened tab. This order will resume here.',
  };
  const failure = (message, code) => Object.assign(new Error(message), {code});
  const retryError = () => failure('This browser read was interrupted. Use Retry order or Check again to start a new read.', 'retry_required');
  function extension(message, timeoutMs = 12000) {
    return new Promise((resolve, reject) => {
      if (!window.chrome?.runtime?.sendMessage) {
        reject(failure('Connect this computer to read eBay orders.', 'setup_required')); return;
      }
      let settled = false;
      const finish = (value, error) => {
        if (settled) return;
        settled = true; clearTimeout(timer);
        if (error) reject(error); else resolve(value);
      };
      const timer = setTimeout(() => finish(null, failure('The browser connection did not respond. Refresh saved status before trying again.', 'browser_timeout')), timeoutMs);
      try {
        window.chrome.runtime.sendMessage(EXTENSION_ID, message, response => {
          const error = window.chrome.runtime.lastError;
          if (error || !response) finish(null, failure('Connect this computer to read eBay orders.', 'setup_required'));
          else finish(response);
        });
      } catch (_) { finish(null, failure('Connect this computer to read eBay orders.', 'setup_required')); }
    });
  }
  async function available() {
    try { return (await extension({type: 'stuffapp.ebay.ping'}, 1500)).ok === true; }
    catch (_) { return false; }
  }
  async function post(body, signal) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (signal?.aborted) abort(); else signal?.addEventListener('abort', abort, {once: true});
    const timer = setTimeout(abort, 15000);
    try {
      const response = await fetch(ENDPOINT, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: {'Accept': 'application/json', 'Content-Type': 'application/json'}, body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok !== true) throw failure(data.error || 'This browser read could not be confirmed. Refresh saved status before trying again.', 'request_unconfirmed');
      return data;
    } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
  }
  function validate(refresh) {
    if (!refresh || refresh.reader !== 'browser' || typeof refresh.id !== 'string' || !refresh.id
        || typeof refresh.order_id !== 'string' || !refresh.order_id || !activeStates.has(refresh.status)) {
      throw failure('The eBay browser request changed. Refresh saved status before trying again.', 'request_changed');
    }
    const expires = Number(refresh.expires_at) * 1000;
    if (!Number.isFinite(expires) || expires <= Date.now()) throw failure('This browser read expired. Retry the order or Check again.', 'expired');
    return Math.min(expires, Date.now() + 600000);
  }
  function notify(job, status) {
    const message = messages[status];
    if (message) job.listeners.forEach(callback => callback(message, {status, id: job.id, order_id: job.order}));
  }
  function cancelled(job) {
    if (job.controller.signal.aborted) throw failure('Browser read stopped. Your saved order is kept.', 'cancelled');
    if (Date.now() >= job.deadline) throw failure('This browser read expired. Retry the order or Check again.', 'expired');
  }
  function correlate(job, response) {
    if (!response || response.ok !== true) throw retryError();
    if (response.id !== job.id || response.order_id !== job.order) {
      throw failure('The browser returned a different order request. Refresh saved status before trying again.', 'request_changed');
    }
  }
  function pause(job) {
    return new Promise((resolve, reject) => {
      const signal = job.controller.signal;
      const abort = () => { clearTimeout(timer); reject(failure('Browser read stopped.', 'cancelled')); };
      const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, Math.max(1, Math.min(1500, job.deadline - Date.now())));
      if (signal.aborted) abort(); else signal.addEventListener('abort', abort, {once: true});
    });
  }
  async function stopExtension(job) {
    if (!job.token) return;
    if (!job.cancelPromise) job.cancelPromise = extension({type: 'stuffapp.ebay.cancel', id: job.id, token: job.token}).catch(() => {});
    await job.cancelPromise;
  }
  async function read(job, refresh) {
    let terminalSubmitted = false;
    try {
      if (!await available()) throw failure('Connect this computer to read eBay orders.', 'setup_required');
      cancelled(job);
      const claim = await post({action: 'claim', id: job.id}, job.controller.signal);
      cancelled(job);
      const request = claim.request;
      if (request?.id !== job.id || request.order_id !== job.order || typeof claim.token !== 'string' || !claim.token
          || Number(request.expires_at) !== Number(refresh.expires_at)) {
        throw failure('The saved browser request changed. Refresh saved status before trying again.', 'request_changed');
      }
      job.token = claim.token;
      const started = await extension({type: 'stuffapp.ebay.start', request, token: job.token});
      cancelled(job); correlate(job, started);
      let lastSession = '';
      while (true) {
        cancelled(job);
        await pause(job);
        cancelled(job);
        const result = await extension({type: 'stuffapp.ebay.poll', id: job.id, token: job.token});
        cancelled(job); correlate(job, result);
        if (result.status === 'reading') { notify(job, result.status); continue; }
        if (['sign_in_required', 'challenge_required'].includes(result.status)) {
          notify(job, result.status);
          if (lastSession !== result.status) {
            await post({action: 'complete', id: job.id, token: job.token, session: {state: result.status}}, job.controller.signal);
            lastSession = result.status;
          }
          continue;
        }
        if (!['complete', 'failed'].includes(result.status)) throw retryError();
        const payload = result.payload;
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)
            || (payload.id !== undefined && payload.id !== job.id)) {
          throw failure('The browser result could not be matched to this order. Refresh saved status before trying again.', 'request_changed');
        }
        // Assign the request capability last, so returned data cannot redirect a
        // completion or change its authority. Server validation remains final.
        terminalSubmitted = true;
        await post({...payload, action: 'complete', id: job.id, token: job.token}, job.controller.signal);
        job.state = 'complete';
        return {status: result.status, id: job.id};
      }
    } catch (error) {
      job.state = 'failed';
      // Never replay an uncertain completion or recover a lost capability. The
      // normal saved-status poll will reveal a completion that landed already.
      if (job.token && !terminalSubmitted && !job.controller.signal.aborted && error.code !== 'cancelled' && error.code !== 'request_changed') {
        try { await post({action: 'complete', id: job.id, token: job.token, error: 'browser'}); } catch (_) {}
      }
      await stopExtension(job);
      throw error;
    }
  }
  function run(refresh, options = {}) {
    try {
      const deadline = validate(refresh);
      const existing = jobs.get(refresh.id);
      if (existing) {
        if (existing.order !== refresh.order_id) throw failure('The eBay order request changed.', 'request_changed');
        existing.deadline = Math.min(existing.deadline, deadline);
        if (options.onProgress) existing.listeners.add(options.onProgress);
        return existing.promise;
      }
      if (refresh.status !== 'queued') throw retryError();
      const job = {id: refresh.id, order: refresh.order_id, deadline, token: '', state: 'reading',
        controller: new AbortController(), listeners: new Set(options.onProgress ? [options.onProgress] : [])};
      jobs.set(job.id, job);
      job.promise = read(job, refresh);
      return job.promise;
    } catch (error) { return Promise.reject(error); }
  }
  function cancel(id) {
    const job = jobs.get(id);
    if (!job || job.state !== 'reading') return Promise.resolve();
    job.controller.abort();
    return stopExtension(job);
  }
  // A page unload never sends a purchase completion. Expiry and explicit retry
  // resolve abandoned claims; only this document can communicate with its tab.
  window.addEventListener('pagehide', () => {
    jobs.forEach(job => { if (job.state === 'reading') { job.controller.abort(); void stopExtension(job); } });
  });
  window.stuffappEbayBrowser = Object.freeze({available, run, cancel, setupUrl: SETUP_URL});
})();
