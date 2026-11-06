const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
const dialogSource = read('static/js/banknote-order-dialog.js');
const detail = read('templates/detail.html');
const detailSource = detail.slice(detail.indexOf('  // ── Coin Check pill:'),
  detail.indexOf('  // ── Coin ✓ Check:'));

function element() {
  return {handlers: {}, dataset: {}, value: '', textContent: '', disabled: false,
    classList: {add() {}, remove() {}}, addEventListener(name, handler) { this.handlers[name] = handler; },
    setAttribute() {}, removeAttribute() {}, focus() {}, showModal() {}, close() {}};
}
const uncertain = () => Object.assign(new Error('The order request could not be confirmed. Refresh saved orders before trying again.'), {uncertain: true});
async function dialogTest(error) {
  const ids = ['banknoteOrderDialog', 'banknoteOrderAdd', 'banknoteOrderForm', 'banknoteOrderNumber',
    'banknoteOrderProcess', 'banknoteOrderCancel', 'banknoteOrderStatus'];
  const nodes = Object.fromEntries(ids.map(id => [id, element()]));
  nodes.banknoteOrderNumber.value = '12-12345-12345';
  let calls = 0; const paths = [];
  vm.runInNewContext(dialogSource, {document: {getElementById: id => nodes[id]}, window: {
    startBanknoteOrderReview: async () => { calls++; throw error; },
    location: {assign: url => paths.push(url)},
  }});
  const submit = () => nodes.banknoteOrderForm.handlers.submit({preventDefault() {}});
  await submit();
  assert.equal(nodes.banknoteOrderProcess.disabled, false);
  assert.equal(nodes.banknoteOrderNumber.readOnly, false);
  if (error.uncertain) {
    assert.equal(nodes.banknoteOrderProcess.textContent, 'Open saved orders');
    nodes.banknoteOrderAdd.handlers.click();
    assert.match(nodes.banknoteOrderStatus.textContent, /could not be confirmed/);
    await submit();
    assert.deepEqual(paths, ['/banknotes/imports/new']);
    assert.equal(calls, 1, 'The recovery action does not replay an uncertain import');
  } else {
    await submit();
    assert.equal(calls, 2, 'A known failure can be retried');
  }
}
async function detailTest(error, changed = false) {
  const button = element(); button.textContent = '✓ Check';
  const form = {inert: false, dataset: {}, children: [], querySelector: () => ({value: '12-12345-12345'})};
  let calls = 0; const paths = [], alerts = []; let values = [['order_number', '12-12345-12345']];
  const window = {banknoteOrderDraftCandidate: () => true,
    startBanknoteOrderReview: async () => { calls++; throw error; },
    location: {assign: url => paths.push(url)}};
  vm.runInNewContext(detailSource, {
    document: {querySelectorAll: () => [button], getElementById: () => form},
    window,
    FormData: class { constructor() { return values; } },
    coinLookupFailureMessage: err => err.message, alert: message => alerts.push(message),
  });
  await button.handlers.click();
  assert.equal(form.inert, false, 'The form is restored after a failed import');
  assert.equal(form.dataset.orderImportPending, undefined, 'Failed imports restore saving and editing');
  assert.equal(button.disabled, false);
  if (error.uncertain) {
    assert.equal(button.textContent, 'Open saved orders');
    assert.match(alerts[0], /could not be confirmed/);
    if (changed) values = [...values, ['notes', 'Unsaved note']];
    await button.handlers.click();
    assert.deepEqual(paths, ['/banknotes/imports/new']);
    assert.equal(window.__stuffAllowUnload, changed ? undefined : true,
      'Only an unchanged order-only form bypasses the location leave guard');
    assert.equal(calls, 1, 'The recovery action does not replay an uncertain import');
  } else {
    assert.equal(button.textContent, '✓ Check');
    await button.handlers.click();
    assert.equal(calls, 2, 'A known failure can be retried');
  }
}
(async () => {
  await dialogTest(uncertain()); await detailTest(uncertain()); await detailTest(uncertain(), true);
  await dialogTest(new Error('Invalid order')); await detailTest(new Error('Invalid order'));
  console.log('Both order entry points route uncertain requests to saved orders without replay.');
})().catch(error => { console.error(error); process.exit(1); });
