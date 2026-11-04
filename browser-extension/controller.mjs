import {readExactOrder, SessionError, CancelledError} from './reader.mjs';

export const APP_ORIGIN = 'https://stuff.armenante.com';
const PREFIX = 'stuffapp.ebay.';
const ACTIVE = new Set(['reading', 'sign_in_required', 'challenge_required']);
const allowedPage = value => {
  try { const url = new URL(value); return url.origin === APP_ORIGIN && !url.username && !url.password; }
  catch { return false; }
};

export function validSender(sender) {
  return !!sender?.tab && Number.isInteger(sender.tab.id) && sender.frameId === 0 &&
    typeof sender.documentId === 'string' && !!sender.documentId && allowedPage(sender.url) &&
    (!sender.origin || sender.origin === APP_ORIGIN);
}

export function validRequest(request, token, now = Date.now()) {
  return request && typeof request.id === 'string' && /^[a-f0-9]{32}$/.test(request.id) &&
    typeof request.order_id === 'string' && /^\d{2}-\d{5}-\d{5}$/.test(request.order_id) &&
    typeof request.expected_account === 'string' && /^[\w.%-]{1,100}$/.test(request.expected_account) &&
    typeof token === 'string' && /^[A-Za-z0-9_-]{24,256}$/.test(token) &&
    Number.isFinite(request.expires_at) && request.expires_at * 1000 > now && request.expires_at * 1000 <= now + 610000 &&
    (request.import_checkout === undefined || typeof request.import_checkout === 'boolean');
}

export function createController(api, {now = () => Date.now(), sleep = ms => new Promise(resolve => setTimeout(resolve, ms)), readOrder = readExactOrder} = {}) {
  const jobs = new Map(), ownedTabs = new Set();
  // Session storage survives worker suspension but is cleared on browser exit.
  // It contains only IDs of tabs this extension created, never account data,
  // tokens, evidence, cookies, or a job that could be replayed after a restart.
  const ready = (async () => {
    const saved = await api.storage.session.get('ownedTabs');
    for (const id of saved.ownedTabs || []) if (Number.isInteger(id)) await api.tabs.remove(id).catch(() => {});
    await api.storage.session.set({ownedTabs:[]});
  })();
  const persistTabs = () => api.storage.session.set({ownedTabs:[...ownedTabs]});
  const clean = async job => {
    const id = job.tabId;
    if (Number.isInteger(id)) {
      job.tabId = null; ownedTabs.delete(id);
      await api.tabs.remove(id).catch(() => {});
      await persistTabs();
    }
  };
  const snapshot = job => ({ok:true, id:job.request.id, order_id:job.request.order_id, status:job.status,
    ...(job.payload ? {payload:job.payload} : {}),
    ...(job.status === 'sign_in_required' || job.status === 'challenge_required' ? {session:{state:job.status}} : {})});
  const check = job => {
    if (job.cancelled || now() - job.lastPoll > 90000) throw new CancelledError();
    if (now() >= job.request.expires_at * 1000) throw new SessionError('expired');
  };
  const run = async job => {
    try {
      check(job);
      let tab;
      try {
        // Installed web apps and popup windows cannot accept additional tabs.
        // Prefer a regular window; create one only when none exists.
        const sourceWindow = await api.windows.get(job.windowId);
        const normalWindows = sourceWindow.type === 'normal' ? [sourceWindow] : await api.windows.getAll({windowTypes:['normal']});
        const normal = normalWindows.find(window => window.focused) || normalWindows[0];
        if (normal) {
          job.windowId = normal.id;
          tab = await api.tabs.create({url:'about:blank', active:false, windowId:normal.id});
        } else {
          const window = await api.windows.create({url:'about:blank', type:'normal', focused:false});
          job.windowId = window.id;
          tab = window.tabs?.[0] || (await api.tabs.query({windowId:window.id}))[0];
        }
        if (!Number.isInteger(tab?.id)) throw new Error('No reader tab');
      } catch { throw new SessionError('browser_access'); }
      job.tabId = tab.id; ownedTabs.add(tab.id); await persistTabs();
      const wait = async () => { check(job); await sleep(1000); check(job); };
      const navigate = async url => {
        check(job); job.targetUrl = url;
        try { await api.tabs.update(job.tabId, {url}); }
        catch { throw new SessionError('browser_access'); }
      };
      const read = async (func, args = []) => {
        while (true) {
          check(job);
          let raw;
          try {
            const tabState = await api.tabs.get(job.tabId);
            if (tabState.status !== 'complete') return {loading:true};
            const results = await api.scripting.executeScript({target:{tabId:job.tabId, frameIds:[0]}, world:'ISOLATED', func, args});
            if (results.length !== 1 || results[0].frameId !== 0 || !results[0].result || typeof results[0].result !== 'object') throw new Error('Invalid page result');
            raw = results[0].result;
          } catch {
            check(job);
            throw new SessionError('browser_access');
          }
          if (raw.session_state === 'sign_in_required' || raw.session_state === 'challenge_required') {
            if (job.status !== raw.session_state) {
              job.status = raw.session_state;
              await api.tabs.update(job.tabId, {active:true});
              await api.windows.update(job.windowId, {focused:true}).catch(() => {});
            }
            await wait();
            continue;
          }
          if (job.status === 'sign_in_required' || job.status === 'challenge_required') {
            if (raw.loading) { await wait(); continue; }
            job.status = 'reading';
            // A provider sign-in may return to Purchases instead of its receipt.
            // Retry only the same fixed destination after confirmed readiness.
            await navigate(job.targetUrl); await wait(); continue;
          }
          return raw;
        }
      };
      const payload = await readOrder(job.request, {navigate, read, wait, checkActive:() => check(job)});
      check(job);
      job.payload = payload; job.status = payload.error ? 'failed' : 'complete';
    } catch (error) {
      if (error instanceof CancelledError || job.cancelled) { job.status = 'cancelled'; job.payload = undefined; }
      else {
        job.status = 'failed';
        job.payload = {id:job.request.id, ...(error.session ? {session:error.session} : {error:'unreadable'})};
      }
    } finally { await clean(job); }
  };

  const handle = async (message, sender) => {
    if (!validSender(sender)) return {ok:false, error:'forbidden'};
    if (!message || typeof message !== 'object' || typeof message.type !== 'string' || !message.type.startsWith(PREFIX)) return {ok:false, error:'invalid_request'};
    await ready;
    for (const [id, job] of jobs) if (!ACTIVE.has(job.status) && job.request.expires_at * 1000 + 60000 < now()) jobs.delete(id);
    if (message.type === PREFIX + 'ping') return {ok:true, version:1, extension_version:'1.0.0'};
    if (message.type === PREFIX + 'start') {
      if (!validRequest(message.request, message.token, now())) return {ok:false, error:'invalid_request'};
      const existing = jobs.get(message.request.id);
      if (existing) {
        if (existing.token !== message.token || existing.sourceTabId !== sender.tab.id || existing.documentId !== sender.documentId ||
            JSON.stringify(existing.request) !== JSON.stringify(message.request)) return {ok:false, error:'forbidden'};
        existing.lastPoll = now();
        return snapshot(existing);
      }
      if ([...jobs.values()].some(job => ACTIVE.has(job.status))) return {ok:false, error:'busy'};
      const job = {request:structuredClone(message.request), token:message.token, sourceTabId:sender.tab.id,
        documentId:sender.documentId, windowId:sender.tab.windowId, status:'reading', lastPoll:now(), cancelled:false};
      jobs.set(job.request.id, job);
      job.finished = run(job);
      return snapshot(job);
    }
    if (![PREFIX + 'poll', PREFIX + 'cancel'].includes(message.type)) return {ok:false, error:'invalid_request'};
    const job = jobs.get(message.id);
    if (!job) return {ok:false, error:'reader_restarted'};
    if (job.token !== message.token || job.sourceTabId !== sender.tab.id || job.documentId !== sender.documentId) return {ok:false, error:'forbidden'};
    job.lastPoll = now();
    if (message.type === PREFIX + 'cancel') {
      job.cancelled = true; job.status = 'cancelled'; job.payload = undefined;
      await clean(job);
    }
    return snapshot(job);
  };
  const tabRemoved = id => {
    for (const job of jobs.values()) if (ACTIVE.has(job.status) && (job.sourceTabId === id || job.tabId === id)) {
      job.cancelled = true; job.status = 'cancelled'; job.payload = undefined;
      void clean(job).catch(() => {});
    }
  };
  return {handle, tabRemoved};
}
