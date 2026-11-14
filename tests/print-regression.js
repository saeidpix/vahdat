'use strict';
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const html = fs.readFileSync('app/index.html', 'utf8');
function extract(start, end) {
  const a = html.indexOf(start), b = html.indexOf(end, a);
  assert(a >= 0 && b > a, 'print functions missing');
  return html.slice(a, b);
}
const fitSource = extract('async function v16CheckPrintFits(', 'async function printWaybill(');
const printSource = extract('async function printWaybill(', "$('#v16PrintFromForm')");
async function fit(fields) {
  const box = { style: {}, innerHTML: '', querySelectorAll: s => s === 'img' ? [] : fields, remove() {} };
  const document = { fonts: { ready: Promise.resolve() }, createElement: () => box, body: { appendChild() {} } };
  const getComputedStyle = el => ({ overflowX: el.overflow || 'hidden', overflowY: el.overflow || 'hidden' });
  return vm.runInNewContext(fitSource + ';v16CheckPrintFits', { document, getComputedStyle, Promise, Array })('<p>test</p>');
}
async function runPrint(fits, direct) {
  const elements = Object.fromEntries(['printArea','v16PreviewPaper','v16PrintNow','v16PreviewNote','v16PreviewWarning','v16PreviewOverlay'].map(id => [id, { innerHTML: '', disabled: true, hidden: true, focus() {} }]));
  let calls = 0, errors = [];
  const ctx = {
    waybillPrintBusy: false, prefs: {}, document: { getElementById: id => elements[id], fonts: { ready: Promise.resolve() }, querySelectorAll: () => [], body: { classList: { add() {} } } },
    window: { autobenzDesktop: { printWaybillSilent: async () => { calls++; return { ok: true }; } } },
    v18ApplyPrintStyle() {}, v16EncodeQr: async () => 'qr', v16QrSvg: () => '<svg/>', v16PrintTicket: () => '<article/>',
    v16CheckPrintFits: async () => fits, toast: s => errors.push(s), console: { error() {} }, Promise, Array
  };
  const fn = vm.runInNewContext(printSource + ';printWaybill', ctx);
  return { result: await fn({ id: '1' }, direct), elements, calls, errors };
}
(async () => {
  const size = (delta, overflow) => ({ scrollHeight: 20 + delta, clientHeight: 20, scrollWidth: 20, clientWidth: 20, overflow });
  assert.strictEqual(await fit([size(5)]), true, 'normal font overhang must fit');
  assert.strictEqual(await fit([size(20, 'visible')]), true, 'visible overflow is not clipped');
  assert.strictEqual(await fit([size(20)]), false, 'actual clipping must be detected');
  let r = await runPrint(false, false);
  assert.strictEqual(r.result, true); assert.strictEqual(r.elements.v16PrintNow.disabled, false, 'preview must remain printable');
  assert(r.elements.v16PreviewWarning.textContent, 'clipping should be warned');
  r = await runPrint(true, true);
  assert.strictEqual(r.result, true); assert.strictEqual(r.calls, 1, 'direct print should reach native handler');
  r = await runPrint(false, true);
  assert.strictEqual(r.result, false); assert.strictEqual(r.calls, 0, 'direct print must stop on genuine clipping');
  console.log('Print fit, preview and direct-print regression tests passed.');
})().catch(e => { console.error(e); process.exit(1); });
