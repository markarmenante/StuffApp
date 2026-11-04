// Read-only DOM readers adapted from Today/apps/today/ebay-purchases.ts.
// Each function is self-contained for chrome.scripting in the isolated world.

export function readPurchasesPage() {

  if (document.readyState !== 'complete') return {error:'Purchases is still loading.'};
  if (/captcha|pardon our interruption|security measure|access denied/i.test(document.title))
    return {error:'eBay security check required.',session_state:'challenge_required'};
  if (/sign in/i.test(document.title) || location.hostname === 'signin.ebay.com')
    return {error:'eBay sign-in required.',session_state:'sign_in_required'};
  if (location.origin !== 'https://www.ebay.com' || location.pathname !== '/mye/myebay/purchase')
    return {error: 'The eBay Purchases page could not be verified.',session_state:'unavailable'};
  const text = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
  const accountLink = document.querySelector('a.m-top-nav__username');
  const account = accountLink ? new URL(accountLink.href).pathname.split('/usr/')[1] : '';
  if (!account && document.querySelector('a[href*="signin.ebay.com"]'))
    return {error:'eBay sign-in required.',session_state:'sign_in_required'};
  const orders = Array.from(document.querySelectorAll('.m-order-card[data-order-id]')).filter(el => el.getClientRects().length);
  if (!document.querySelector('.pagination [aria-current="page"]') && !false)
    return {error: 'Purchases is still loading; no partial update was sent.'};
  if (!account || !orders.length) return {error: 'Purchases is not ready or its layout has changed.'};
  const items = [];
  for (const order of orders) {
    const header = order.querySelector('.section-notice__main');
    const status = text(header?.querySelector('.primaryMessage'));
    const date = Array.from(header?.querySelectorAll('.secondaryMessage .primary__item--wrapper') || [])
      .find(el => text(el.querySelector('.primary__item--item-text-label')) === 'Order date:');
    const ordered_date = text(date?.lastElementChild);
    const rows = Array.from(order.querySelectorAll('[input-listing-id]')).filter(el => el.getClientRects().length);
    if (!rows.length) {
      items.push({order_id: order.getAttribute('data-order-id')});
      continue;
    }
    for (const row of rows) {
      const title = text(row.querySelector('.title-heading'));
      const sellerLink = row.querySelector('a[href*="/usr/"]');
      const seller = sellerLink ? new URL(sellerLink.href).pathname.split('/usr/')[1] : '';
      const qty = row.innerText.match(/\b(?:Quantity|Qty)\s*:?\s*(\d+)\b/i);
      items.push({order_id: order.getAttribute('data-order-id'), item_id: row.getAttribute('input-listing-id'),
        title, seller, quantity: qty ? Number(qty[1]) : 1, status_text: status, ordered_date,
        details_url: order.querySelector('a.m-ph-order-info-cta')?.href,
        delivery_text: text(row.querySelector('.fake-notice__title'))});
    }
  }
  const next = document.querySelector('button.pagination__next');
  return {account, items, page: Number(text(document.querySelector('.pagination [aria-current="page"]')) || '1'),
    hasNext: !!next && !next.disabled && next.getAttribute('aria-disabled') !== 'true' && !!next.getAttribute('data-href')};
}

export function readReceiptPage(orderId, itemId) {
  if (!/^\d{2}-\d{5}-\d{5}$/.test(orderId)) return {blocked:true};
  if (!/^\d{9,15}$/.test(itemId)) return {blocked:true};

    if (document.readyState !== 'complete') return {loading:true};
    if (/captcha|pardon our interruption|security measure|access denied/i.test(document.title))
      return {blocked:true,error:'eBay security check required.',session_state:'challenge_required'};
    if (/sign in/i.test(document.title) || location.hostname === 'signin.ebay.com')
      return {blocked:true,error:'eBay sign-in required.',session_state:'sign_in_required'};
    if (location.origin !== 'https://order.ebay.com' || location.pathname !== '/ord/show' ||
        new URLSearchParams(location.search).get('orderId') !== orderId)
      return {blocked:true};
    const text = el => (el?.textContent || '').replace(/\s+/g,' ').trim();
    const links = [...document.querySelectorAll('a.item-page-content-link')].filter(a=>a.getClientRects().length);
    const cards = [...new Set(links.map(a=>a.closest('div.card-content-box')).filter(Boolean))];
    if (!cards.length) return {loading:true};
    const exactLinks = links.filter(a=> {
      try { const u=new URL(a.href); return u.origin === 'https://www.ebay.com' && new RegExp('^/itm/(?:[^/]+/)?' + itemId + '/?$').test(u.pathname); }
      catch { return false; }
    });
    const exactCards = [...new Set(exactLinks.map(a=>a.closest('div.card-content-box')).filter(Boolean))];
    if (exactCards.length !== 1) return {blocked:true};
    const card = exactCards[0];
    // Summary labels alone detect order-level adjustments; never read their
    // values or the neighboring payment method/address panels.
    const summaryLabels = [...document.querySelectorAll('dt.eui-label')].map(text);
    if (summaryLabels.some(t=>/\b(refund\w*|discount\w*|coupon\w*)\b/i.test(t))) return {blocked:true};
    // eBay renders the receipt in stages after document.readyState is complete.
    // Missing summary/item fields are not yet evidence of an unreadable price.
    const summaryReady = !!document.querySelector('.payment-info-title') && summaryLabels.some(t=>/^Order total$/i.test(t));
    const link = links.find(a=> {
      try { const u=new URL(a.href); return u.origin === 'https://www.ebay.com' && new RegExp('^/itm/(?:[^/]+/)?' + itemId + '/?$').test(u.pathname); }
      catch { return false; }
    });
    const body = text(card);
    if (!link || body.length > 12000 || /\b(refund\w*|cancelled|canceled|discount\w*|coupon\w*)\b/i.test(body))
      return {blocked:true};
    // Adjacent DOM nodes can join the numeric ID directly to a label (for
    // example, No cancellations). Reject additional digits, not adjoining text.
    const ids = [...body.matchAll(/Item number:\s*(\d{9,15})(?!\d)/gi)].map(m=>m[1]);
    if (ids.length && (ids.length !== 1 || ids[0] !== itemId)) return {blocked:true};
    const quantities = [...body.matchAll(/\b(?:Quantity|Qty)\s*:?\s*(\d+)\b/gi)].map(m=>Number(m[1]));
    if (quantities.some(q=>q!==1)) return {blocked:true};
    if (!ids.length || !summaryReady) return {loading:true};
    const labels = [...new Set([...card.querySelectorAll('span.clipped')].map(text).filter(t=>/^Unit price\b/i.test(t)))];
    const currencies = [...new Set([...card.querySelectorAll('[itemprop="priceCurrency"], [data-currency]')]
      .map(el=>el.getAttribute('content')||el.getAttribute('data-currency')||text(el)).filter(Boolean))];
    return {order_id:orderId,item_id:itemId,title:text(link),labels,currencies};
  }

export function readReceiptInventory(orderId) {
  if (!/^\d{2}-\d{5}-\d{5}$/.test(orderId)) return {blocked:true};

    if (document.readyState !== 'complete') return {loading:true};
    if (/captcha|pardon our interruption|security measure|access denied/i.test(document.title))
      return {blocked:true,session_state:'challenge_required'};
    if (/sign in/i.test(document.title) || location.hostname === 'signin.ebay.com')
      return {blocked:true,session_state:'sign_in_required'};
    if (location.origin !== 'https://order.ebay.com' || location.pathname !== '/ord/show' ||
        new URLSearchParams(location.search).get('orderId') !== orderId) return {blocked:true};
    const links = [...document.querySelectorAll('a.item-page-content-link')].filter(a=>a.getClientRects().length);
    const cards = [...new Set(links.map(a=>a.closest('div.card-content-box')).filter(Boolean))];
    if (!cards.length || !document.querySelector('.payment-info-title')) return {loading:true};
    const ids = cards.map(c=> [...(c.textContent || '').matchAll(/Item number:\s*(\d{9,15})(?!\d)/gi)].map(m=>m[1]));
    if (ids.some(i=>i.length > 1) || cards.length > 25) return {blocked:true};
    if (ids.some(i=>!i.length)) return {loading:true};
    if (new Set(ids.flat()).size !== cards.length) return {blocked:true};
    return {item_ids:ids.flat()};
  }

export function readListingPage(itemId) {
  if (!/^\d{9,15}$/.test(itemId)) return {blocked:true};

    if (document.readyState !== 'complete') return {loading:true};
    if (/captcha|pardon our interruption|security measure|access denied/i.test(document.title))
      return {blocked:true,error:'eBay security check required.',session_state:'challenge_required'};
    if (/sign in/i.test(document.title) || location.hostname === 'signin.ebay.com')
      return {blocked:true,error:'eBay sign-in required.',session_state:'sign_in_required'};
    if (location.origin !== 'https://www.ebay.com' || !new RegExp('^/itm/(?:[^/]+/)?' + itemId + '/?$').test(location.pathname))
      return {blocked:true};
    const text = el => {
      if (!el) return '';
      const node = el.cloneNode(true);
      node.querySelectorAll('script,style,button,svg,noscript').forEach(e => e.remove());
      node.querySelectorAll('br').forEach(e => e.replaceWith('\n'));
      node.querySelectorAll('div,p,li,h1,h2,h3,h4,tr,td,th,dt,dd,section').forEach(e => e.append('\n'));
      return node.textContent.split('\n').map(s=>s.replace(/\s+/g,' ').trim()).filter(Boolean).join('\n');
    };
    const main = document.querySelector('main') || document;
    const title = text(main.querySelector('h1'));
    if (/daily limit|exceeded.*requests|try.*tomorrow/i.test(main.textContent)) return {blocked:true};
    const sections = ['.x-price-section','.x-item-condition','.x-item-description','.x-about-this-item']
      .map(s=>text(main.querySelector(s))).filter(Boolean);
    if (title.length < 12 || title.length > 500 || !sections.length ||
        /listing.*(?:removed|unavailable)|page.*(?:missing|not found)/i.test(title)) return {blocked:true};
    const images = [...main.querySelectorAll('.ux-image-carousel img')]
      .map(e=>e.getAttribute('data-zoom-src')||e.getAttribute('data-src')||e.src);
    const cover = document.querySelector('meta[property="og:image"]')?.content;
    if (cover) images.push(cover);
    return {url:'https://www.ebay.com/itm/' + itemId,title,
      text: (title+'\neBay item number: ' + itemId + '\n'+sections.join('\n\n')).slice(0,60000),
      images:[...new Set(images.filter(u=>/^https:\/\/i\.ebayimg\.com\/images\/g\/[\w~-]+\/s-l\d+\.(?:jpg|jpeg|png|webp)$/.test(u))
        .map(u=>u.replace(/s-l\d+\./,'s-l1600.')))].slice(0,24)};
  }
