import {checkoutItems, receiptFromPage, validatePage} from './evidence.mjs';
import {readPurchasesPage, readReceiptPage, readReceiptInventory, readListingPage} from './page-readers.mjs';

export const PURCHASES_URL = 'https://www.ebay.com/mye/myebay/purchase';
export class SessionError extends Error {
  constructor(reason) { super('eBay session unavailable'); this.fatal = true; this.session = {state:'unavailable', reason}; }
}
export class CancelledError extends Error { constructor() { super('Cancelled'); this.fatal = true; } }

// No address, payment, messages, cookies or unrelated purchase data leaves this
// reader. host owns a new tab and supplies only fixed, bundled DOM functions.
export async function readExactOrder(request, host) {
  const orderId = request.order_id;
  const items = new Map();
  let previousSignature = '';
  const verifyAccount = account => {
    if (account.toLowerCase() !== request.expected_account.toLowerCase()) throw new SessionError('wrong_account');
  };
  await host.navigate(PURCHASES_URL);
  for (let page = 1; page <= 40; page++) {
    let result, signature = '', stable = 0;
    for (let attempt = 0; attempt < 30; attempt++) {
      await host.wait();
      const raw = await host.read(readPurchasesPage);
      if (typeof raw?.account === 'string') verifyAccount(raw.account);
      try {
        const candidate = validatePage(raw);
        const next = JSON.stringify(candidate);
        if (candidate.page === page && next !== previousSignature) {
          stable = next === signature ? stable + 1 : 0;
          signature = next;
          if (stable >= 2 && (!candidate.skipped.length || attempt >= 7)) {
            result = candidate; previousSignature = signature; break;
          }
        }
      } catch (error) { if (error.fatal) throw error; }
    }
    if (!result) throw new Error('Purchase page did not stabilize');
    verifyAccount(result.account);
    if (result.skipped.some(item => item.order_id === orderId)) throw new Error('Requested order is incomplete');
    const exact = result.items.filter(item => item.order_id === orderId);
    if (exact.length) {
      let ordered = exact, checkout;
      if (request.import_checkout) {
        const selected = checkoutItems(orderId, [...items.values(), ...result.items]);
        ordered = selected.items; checkout = selected.checkout;
        if (!checkout) throw new Error('Checkout membership is unavailable');
      }
      if (ordered.length > 25 || ordered.some(item => item.identity_ambiguous)) throw new Error('Ambiguous order');
      const receipts = [], listings = [];
      if (request.import_checkout) {
        await host.navigate('https://order.ebay.com/ord/show?orderId=' + orderId);
        let confirmed = false;
        for (let attempt = 0; attempt < 12; attempt++) {
          await host.wait();
          const raw = await host.read(readReceiptInventory, [orderId]);
          if (raw.loading) continue;
          if (!raw.blocked && Array.isArray(raw.item_ids)) {
            confirmed = JSON.stringify(raw.item_ids.slice().sort()) === JSON.stringify(ordered.map(i => i.item_id).sort());
          }
          break;
        }
        if (!confirmed) throw new Error('Complete checkout inventory does not match');
      }
      if (ordered.length === 1 || request.import_checkout) {
        for (const item of ordered) {
          if (item.quantity !== 1 || item.identity_ambiguous) continue;
          await host.navigate('https://order.ebay.com/ord/show?orderId=' + item.order_id);
          for (let attempt = 0; attempt < 10; attempt++) {
            await host.wait();
            const raw = await host.read(readReceiptPage, [item.order_id, item.item_id]);
            if (raw.blocked) break;
            if (raw.loading) continue;
            if (raw.order_id !== item.order_id || raw.item_id !== item.item_id) break;
            const receipt = receiptFromPage(raw, item);
            if (receipt) { receipts.push(receipt); break; }
          }
          await host.navigate('https://www.ebay.com/itm/' + item.item_id);
          for (let attempt = 0; attempt < 12; attempt++) {
            await host.wait();
            const raw = await host.read(readListingPage, [item.item_id]);
            if (raw.loading) continue;
            if (!raw.blocked && raw.url === 'https://www.ebay.com/itm/' + item.item_id &&
                typeof raw.text === 'string' && raw.text.length >= 40) listings.push({...raw, item_id:item.item_id});
            break;
          }
        }
      }
      // Reconfirm the buyer after every read, including a missing receipt.
      await host.navigate(PURCHASES_URL);
      let confirmed = false;
      for (let attempt = 0; attempt < 10; attempt++) {
        await host.wait();
        const raw = await host.read(readPurchasesPage);
        if (typeof raw?.account === 'string') verifyAccount(raw.account);
        try { validatePage(raw); confirmed = true; break; } catch (error) { if (error.fatal) throw error; }
      }
      if (!confirmed) throw new Error('Buyer could not be reconfirmed');
      host.checkActive();
      return {id:request.id, account:result.account, observed_at:new Date().toISOString(), items:ordered,
        pages:page, skipped:[], listings, receipts, ...(checkout ? {checkout} : {})};
    }
    for (const item of result.items) {
      const key = item.order_id + ':' + item.item_id;
      const previous = items.get(key);
      items.set(key, previous ? {...previous, identity_ambiguous:true} : item);
    }
    if (!result.hasNext) return {id:request.id, error:'not_found'};
    const advanced = await host.read(nextPurchasePage, [page]);
    if (!advanced?.advanced) throw new Error('Purchase pagination could not be verified');
  }
  throw new Error('Purchase history exceeded the page limit');
}

// The sole click is the already-rendered purchase-history pager. This cannot
// click checkout, pay, buy, watch, sign-in, consent or verification controls.
export function nextPurchasePage(page) {
  if (location.origin !== 'https://www.ebay.com' || location.pathname !== '/mye/myebay/purchase') return {blocked:true};
  const current = document.querySelector('.pagination [aria-current="page"]');
  const next = document.querySelector('button.pagination__next');
  if (Number(current?.textContent?.trim()) !== page || !next || next.disabled || next.getAttribute('aria-disabled') === 'true') return {blocked:true};
  try {
    const target = new URL(next.getAttribute('data-href'), location.href);
    if (target.origin !== 'https://www.ebay.com' || target.pathname !== '/mye/myebay/purchase') return {blocked:true};
  } catch { return {blocked:true}; }
  next.click();
  return {advanced:true};
}
