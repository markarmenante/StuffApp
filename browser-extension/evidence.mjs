// Evidence validation adapted from Today/apps/today/ebay-purchases.ts.
const ORDER_ID = /^(?:\d{2}-\d{5}-\d{5}|\d{9,15}(?:-\d{1,15})?)$/;
const USERNAME = /^[\w.*%-]+$/;
export function checkoutItems(orderId, candidates) {
    const details = (item)=>{
        try {
            const u = new URL(item.details_url || "");
            const group = u.searchParams.get("purchaseOrderId");
            if (u.origin !== "https://order.ebay.com" || u.pathname !== "/ord/show" || u.username || u.password || u.hash || u.searchParams.getAll("orderId").length !== 1 || u.searchParams.get("orderId") !== item.order_id || u.searchParams.getAll("purchaseOrderId").length !== 1 || !/^\d{2}-\d{4}-\d{6}$/.test(group || "")) return;
            return {
                group: group,
                url: u.href
            };
        } catch  {
            return;
        }
    };
    const original = candidates.filter((i)=>i.order_id === orderId);
    const groups = [
        ...new Set(original.map((i)=>details(i)?.group).filter(Boolean))
    ];
    if (!original.length || groups.length > 1) throw new Error("Checkout identity is ambiguous");
    if (!groups.length) return {
        items: original
    };
    const selected = candidates.filter((i)=>details(i)?.group === groups[0]);
    if (selected.length > 25 || original.some((i)=>!selected.includes(i)) || new Set(selected.map((i)=>i.item_id)).size !== selected.length || selected.some((i)=>i.identity_ambiguous)) throw new Error("Checkout items are ambiguous");
    const orders = [
        ...new Set(selected.map((i)=>i.order_id))
    ].map((id)=>({
            order_id: id,
            details_url: details(selected.find((i)=>i.order_id === id)).url,
            item_ids: selected.filter((i)=>i.order_id === id).map((i)=>i.item_id)
        }));
    return {
        items: selected,
        checkout: {
            requested_order_id: orderId,
            purchase_order_id: groups[0],
            orders
        }
    };
}
export function receiptFromPage(raw, item) {
    const p = raw;
    if (!p || typeof p !== "object" || p.order_id !== item.order_id || p.item_id !== item.item_id || item.quantity !== 1 || item.identity_ambiguous || /\b(refund\w*|cancelled|canceled|discount\w*|coupon\w*)\b/i.test(item.status_text + " " + item.delivery_text) || typeof p.title !== "string" || p.title.length < 5 || p.title.length > 500 || !Array.isArray(p.labels) || p.labels.length !== 1 || typeof p.labels[0] !== "string" || !Array.isArray(p.currencies) || p.currencies.length > 1) return;
    const match = /^Unit price\s+(US\s*\$|USD|EUR|€|GBP|£|\$)\s*((?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})$/i.exec(p.labels[0]);
    if (!match) return;
    const token = match[1].toUpperCase();
    const explicit = /^(?:US\s*\$|USD)$/.test(token) ? "USD" : /^(EUR|€)$/.test(token) ? "EUR" : /^(GBP|£)$/.test(token) ? "GBP" : undefined;
    const attribute = p.currencies[0];
    if (attribute !== undefined && ![
        "USD",
        "EUR",
        "GBP"
    ].includes(String(attribute))) return;
    if (explicit && attribute && explicit !== attribute) return;
    const currency = explicit || attribute || (token === "$" ? "$" : undefined);
    if (!currency || token === "$" && currency !== "USD" && currency !== "$") return;
    const amount = match[2].replaceAll(",", "");
    if (!(Number(amount) > 0 && Number(amount) <= 1000000)) return;
    return {
        order_id: item.order_id,
        item_id: item.item_id,
        quantity: 1,
        url: "https://order.ebay.com/ord/show?orderId=" + item.order_id,
        currency,
        unit_amount: amount,
        observed_at: new Date().toISOString(),
        evidence: `Order number ${item.order_id}\nItem info\n${p.title}\n${p.labels[0]}\nCurrency: ${currency}\nItem number: ${item.item_id}`
    };
}
export function validatePage(raw) {
    const p = raw;
    if (!p || typeof p !== "object") throw new Error("eBay Purchases returned an unreadable page");
    if (p.error) throw new Error(String(p.error).slice(0, 200));
    if (typeof p.account !== "string" || !/^[\w.%-]{1,100}$/.test(p.account) || !Number.isInteger(p.page) || Number(p.page) < 1 || typeof p.hasNext !== "boolean" || !Array.isArray(p.items) || !p.items.length || p.items.length > 200) throw new Error("eBay Purchases layout needs review; no statuses were changed");
    const skipped = new Map();
    const blocked = new Set();
    const items = new Map();
    for (const [index, rawItem] of p.items.entries()){
        const item = rawItem;
        const fields = [];
        if (!item || typeof item.order_id !== "string" || !ORDER_ID.test(item.order_id)) fields.push("order_id");
        if (!item || typeof item.item_id !== "string" || !/^\d{9,15}$/.test(item.item_id)) fields.push("item_id");
        if (!item || !Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 999) fields.push("quantity");
        for (const [key, limit] of [
            [
                "title",
                500
            ],
            [
                "seller",
                150
            ],
            [
                "status_text",
                300
            ],
            [
                "ordered_date",
                40
            ]
        ]){
            if (typeof item?.[key] !== "string" || !item[key].trim() || item[key].length > limit) fields.push(key);
        }
        if (typeof item?.seller === "string" && !USERNAME.test(item.seller) && !fields.includes("seller")) fields.push("seller");
        if (typeof item?.delivery_text !== "string" || item.delivery_text.length > 500) fields.push("delivery_text");
        if (fields.length || !item) {
            const orderId = !fields.includes("order_id") ? item.order_id : undefined;
            if (orderId) blocked.add(orderId);
            const key = orderId ?? `row:${index}`;
            if (!skipped.has(key)) skipped.set(key, {
                order_id: orderId,
                page: Number(p.page),
                reason: `Unreadable fields: ${fields.join(", ")}`
            });
            continue;
        }
        const key = item.order_id + ":" + item.item_id;
        const previous = items.get(key);
        items.set(key, previous ? {
            ...previous,
            identity_ambiguous: true
        } : item);
    }
    return {
        account: p.account,
        page: Number(p.page),
        hasNext: p.hasNext,
        items: [
            ...items.values()
        ].filter((item)=>!blocked.has(item.order_id)),
        skipped: [
            ...skipped.values()
        ]
    };
}
