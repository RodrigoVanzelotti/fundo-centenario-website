const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('frontend/como-apoiar/index.html', 'utf8');
assert.match(html, /id="donorStep" hidden disabled/);
assert.match(html, /data-progress="payment"/);
assert(!html.includes('??'));
assert(html.indexOf('id="customAmount"') < html.indexOf('id="donorStep"'));
assert(html.indexOf('name="program"') < html.indexOf('id="donorName"'));

async function check(method, missingReturnSession = false, optionsFailure = false) {
  const nodes = new Map();
  const node = (selector) => {
    if (!nodes.has(selector)) nodes.set(selector, {
      value: '', hidden: false, disabled: false, checked: false,
      dataset: {}, validity: { badInput: false }, listeners: {},
      classList: { toggle() {}, remove() {}, add() {} },
      addEventListener(type, callback) { this.listeners[type] = callback; },
      querySelector(selector) {
        if (selector === 'input') return this.radio;
        if (selector.startsWith("input[name='method']")) {
          return radios.find(radio => !radio.disabled && (!selector.includes(':checked') || radio.checked));
        }
        return node('#submit');
      },
      reportValidity() { return true; },
      setAttribute() {}, removeAttribute() {}, focus() {},
    });
    return nodes.get(selector);
  };
  const form = node('#donationQuestionnaire');
  const radios = ['pix', 'pix_automatico', 'card', 'card_recurring'].map(value => ({ value, disabled: false, checked: value === method }));
  const methodOptions = radios.map(radio => ({ ...node(`option-${radio.value}`), radio }));
  form.elements = { method: { get value() { return radios.find(radio => radio.checked && !radio.disabled)?.value || ''; } }, program: { value: 'geral' } };
  node('#donorStep').hidden = node('#donorStep').disabled = true;
  node('#paymentStage').hidden = node('#successStage').hidden = true;
  node('#donorName').value = 'Test Donor';
  node('#donorEmail').value = 'test@example.com';
  node('#donorCpf').value = '52998224725';
  node('#formStatus').textContent = 'Stale error';
  const requests = [];
  const timers = [];
  const windowListeners = {};
  let restoredUrl = null;
  let status = 'pending';
  let failIntent = true;
  vm.runInNewContext(fs.readFileSync('frontend/assets/js/donation.js', 'utf8'), {
    document: { querySelector: node, querySelectorAll: selector => selector === '.payment-method-option' ? methodOptions : [], hidden: false },
    window: {
      location: { href: `https://example.com/como-apoiar/${missingReturnSession ? '?donation_id=old&keep=1#contribuir' : ''}`, assign(url) { requests.push({ redirect: url }); } },
      addEventListener(type, callback) { windowListeners[type] = callback; },
      scrollTo() {}, setInterval(callback) { timers.push(callback); return 1; }, clearInterval() {},
    },
    sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    history: { replaceState(state, title, url) { restoredUrl = url; } }, URL, Intl, setTimeout(callback) { callback(); },
    async fetch(url, options) {
      requests.push({ url, options });
      if (url.endsWith('/options')) return { ok: !optionsFailure, json: async () => ({ methods: method === 'pix_automatico' ? radios.map(radio => radio.value) : ['pix', 'card', 'card_recurring'] }) };
      if (url.endsWith('/intents') && failIntent) return { ok: false, json: async () => ({ detail: 'Try again' }) };
      return { ok: true, json: async () => ({
        donation_id: 'test', status_token: 'token', method, amount_cents: 25000,
        program_label: 'General', status, persisted: status === 'paid',
        pix_copy_paste: method === 'pix' ? 'pix-code' : null,
        redirect_url: method === 'pix' ? null : 'https://example.com/checkout',
      }) };
    },
  });
  // Options are fetched asynchronously before the form can create a payment.
  await new Promise(resolve => setImmediate(resolve));
  if (optionsFailure) {
    assert.equal(node('#submit').disabled, true);
    assert.equal(node('#formStatus').hidden, false);
    await form.listeners.submit({ preventDefault() {} });
    assert(!requests.some(request => request.url?.endsWith('/intents')));
    return;
  }
  assert.equal(methodOptions.find(option => option.radio.value === 'pix_automatico').hidden, method !== 'pix_automatico');
  assert.equal(methodOptions.find(option => option.radio.value === 'card_recurring').hidden, false);
  const intentRequests = () => requests.filter(request => request.url?.endsWith('/intents'));
  if (missingReturnSession) {
    assert.equal(node('#formStatus').hidden, false);
    assert.equal(restoredUrl, '/como-apoiar/?keep=1#contribuir');
  } else {
    assert.equal(node('#formStatus').hidden, true);
    assert.equal(node('#formStatus').textContent, '');
  }
  const submit = () => form.listeners.submit({ preventDefault() {} });
  node('#customAmount').value = '-5';
  node('#customAmount').reportValidity = () => false;
  await submit();
  assert.equal(node('#donorStep').hidden, true);
  assert.equal(intentRequests().length, 0);
  for (const type of ['input', 'change', 'click', 'reset']) {
    assert.equal(node('#formStatus').hidden, false);
    form.listeners[type]();
    assert.equal(node('#formStatus').hidden, true);
    assert.equal(node('#formStatus').textContent, '');
    await submit(); // An invalid submission still displays a fresh error.
  }
  windowListeners.pageshow({ persisted: true });
  assert.equal(node('#formStatus').hidden, true);
  node('#customAmount').value = '250';
  node('#customAmount').reportValidity = () => true;
  await submit();
  assert.equal(node('#contributionStep').hidden, true);
  assert.equal(node('#donorStep').disabled, false);
  assert.equal(intentRequests().length, 0);
  node('#backToContribution').listeners.click();
  assert.equal(node('#donorStep').disabled, true);
  assert.equal(node('#donorName').value, 'Test Donor');
  await submit();
  form.reportValidity = () => false;
  await submit();
  assert.equal(intentRequests().length, 0);
  form.reportValidity = () => true;
  node('#donorCpf').value = '11111111111';
  await submit();
  assert.equal(intentRequests().length, 0);
  node('#donorCpf').value = '52998224725';
  await submit();
  assert.equal(node('#paymentStage').hidden, true);
  assert.equal(node('#submit').disabled, false);
  assert.equal(node('#backToContribution').disabled, false);
  failIntent = false;
  const creating = submit();
  await submit(); // Double submission must not create another intent.
  await creating;
  assert.equal(requests.filter(r => r.url?.endsWith('/intents')).length, 2);
  const payload = JSON.parse(requests.findLast(r => r.url?.endsWith('/intents')).options.body);
  assert.equal(payload.amount_cents, 25000);
  assert.equal(payload.method, method);
  assert.equal(node('#paymentStage').hidden, false);
  assert.equal(node('#successStage').hidden, true);
  if (method === 'pix') assert.equal(node('#pixCode').value, 'pix-code');
  else assert(requests.some(r => r.redirect === 'https://example.com/checkout'));
  status = 'paid';
  await timers[0]();
  assert.equal(node('#successStage').hidden, false);
}

(async () => {
  for (const method of ['pix', 'pix_automatico', 'card', 'card_recurring']) await check(method);
  await check('pix', true);
  await check('card_recurring', false, true);
  console.log('donation steps: ok');
})().catch(error => { console.error(error); process.exitCode = 1; });
