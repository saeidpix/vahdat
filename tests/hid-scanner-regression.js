'use strict';
const assert = require('assert');
const fs = require('fs');
const hid = require('../app/hid-scanner.js');

function key(code, shiftKey, keyText) {
  return { code, shiftKey: !!shiftKey, key: keyText || 'ح', ctrlKey: false,
    altKey: false, metaKey: false, isComposing: false,
    prevented: false, stopped: false,
    preventDefault() { this.prevented = true; },
    stopPropagation() { this.stopped = true; } };
}
assert.strictEqual(hid.usCharacter(key('KeyA', true)), 'A');
assert.strictEqual(hid.usCharacter(key('KeyA', false)), 'a');
assert.strictEqual(hid.usCharacter(key('KeyZ', true)), 'Z');
assert.strictEqual(hid.usCharacter(key('Digit1', true)), '!');
assert.strictEqual(hid.usCharacter(key('Digit0', true)), ')');
assert.strictEqual(hid.usCharacter(key('Digit7', false)), '7');
assert.strictEqual(hid.usCharacter(key('Numpad7', false)), '7');
assert.strictEqual(hid.usCharacter(key('Period', false)), '.');
assert.strictEqual(hid.usCharacter(key('Minus', true)), '_');
assert.strictEqual(hid.usCharacter(key('Minus', false)), '-');
assert.strictEqual(hid.usCharacter(key('Backslash', false)), '\\');
assert.strictEqual(hid.usCharacter(key('', false, 'ک')), null);
assert.strictEqual(hid.usCharacter(key('', false, 'A')), 'A');

assert(hid.isValidScan('ABV16.Z.Abc123_-'));
assert(hid.isValidScan('ABV16.B.aBc09_-'));
assert(hid.isValidScan('۱۲۳'));
assert(!hid.isValidScan('ABV16.Z.'));
assert(!hid.isValidScan('ABV16.X.bad'));
assert(!hid.isValidScan('فرستنده'));

function element(id) {
  const e = {
    id, value: '', maxLength: 12000, selectionStart: 0, selectionEnd: 0,
    events: [], focusCount: 0, disabled: false, readOnly: false,
    classList: { add() {} },
    focus() { this.focusCount++; },
    dispatchEvent(ev) { this.events.push(ev.type); },
    addEventListener(type, fn) { this[type] = fn; },
    setRangeText(ch, start, end) {
      this.value = this.value.slice(0, start) + ch + this.value.slice(end);
      this.selectionStart = this.selectionEnd = start + ch.length;
    }
  };
  return e;
}
const elements = Object.fromEntries(['v16ScanInput', 'v19WaybillCode',
  'v22QrScanInput', 'v22Search', 'v22Msg', 'v22QrSubmit',
  'senderName'].map(id => [id, element(id)]));
const handlers = {};
const doc = {
  getElementById: id => elements[id],
  addEventListener(type, fn, capture) { if (type === 'keydown' && capture) handlers.keydown = fn; }
};
let received = [];
const host = { barresanReleaseScan: raw => received.push(raw) };
hid.install(doc, host);
function press(el, code, shiftKey, keyText) {
  const e = key(code, shiftKey, keyText);
  e.target = el;
  handlers.keydown(e);
  return e;
}
function scan(el, value) {
  for (const ch of value) {
    const upper = /^[A-Z]$/.test(ch), lower = /^[a-z]$/.test(ch);
    let code = upper || lower ? 'Key' + ch.toUpperCase() : '';
    let shift = upper;
    if (!code && /^[0-9]$/.test(ch)) code = 'Digit' + ch;
    if (ch === '.') code = 'Period';
    if (ch === '-') code = 'Minus';
    if (ch === '_') { code = 'Minus'; shift = true; }
    assert(code, 'unsupported test character: ' + ch);
    const event = press(el, code, shift, 'ض'); // simulate Persian Windows layout
    assert(event.prevented && event.stopped, 'HID character must bypass Persian layout');
  }
}
const payload = 'ABV16.Z.aB93_K-l00Z';
scan(elements.v16ScanInput, payload);
assert.strictEqual(elements.v16ScanInput.value, payload);
assert(elements.v16ScanInput.events.includes('input'));
assert(!press(elements.v16ScanInput, 'Enter', false, 'Enter').prevented,
  'existing destination Enter flow must continue');
scan(elements.v19WaybillCode, payload);
assert.strictEqual(elements.v19WaybillCode.value, payload);
assert(!press(elements.v19WaybillCode, 'Enter', false, 'Enter').prevented,
  'existing handover Enter flow must continue');
scan(elements.v22QrScanInput, payload);
assert.strictEqual(elements.v22QrScanInput.value, payload);
const submitted = press(elements.v22QrScanInput, 'Enter', false, 'Enter');
assert(submitted.prevented && submitted.stopped);
assert.deepStrictEqual(received, [payload]);
assert.strictEqual(elements.v22QrScanInput.value, '');
scan(elements.v22QrScanInput, 'ABV16.Z.');
press(elements.v22QrScanInput, 'Enter', false, 'Enter');
assert.deepStrictEqual(received, [payload], 'incomplete QR must not reach release');
assert(elements.v22Msg.textContent.includes('نامعتبر'));
scan(elements.v22QrScanInput, '123');
elements.v22QrSubmit.click();
assert.deepStrictEqual(received, [payload, '123'], 'button/manual QR entry supported');

const persianField = elements.senderName;
const ordinary = press(persianField, 'KeyA', false, 'ش');
assert(!ordinary.prevented && !ordinary.stopped);
const search = elements.v22Search;
assert(!press(search, 'KeyR', false, 'ق').prevented, 'Persian name search untouched');
const pasted = key('KeyV', false, 'v');
pasted.ctrlKey = true; pasted.target = elements.v16ScanInput;
handlers.keydown(pasted);
assert(!pasted.prevented, 'Ctrl+V paste must keep working');
const unknown = press(elements.v16ScanInput, '', false, 'فارسی');
assert(!unknown.prevented, 'unknown HID code is not mis-decoded');
elements.v16ScanInput.value = '';
elements.v16ScanInput.selectionStart = elements.v16ScanInput.selectionEnd = 0;
elements.v16ScanInput.maxLength = 2;
scan(elements.v16ScanInput, 'AB');
press(elements.v16ScanInput, 'KeyC', false, 'ض');
assert.strictEqual(elements.v16ScanInput.value, 'AB', 'respect max length');

const html = fs.readFileSync('app/index.html', 'utf8');
for (const id of ['v16ScanInput', 'v19WaybillCode', 'v22QrScanInput', 'v22QrSubmit']) {
  assert(html.includes('id="' + id + '"'), 'missing UI field ' + id);
}
assert(html.includes('<script src="hid-scanner.js"></script>'));
assert(html.includes('window.barresanReleaseScan=function(raw)'));
assert(html.includes("q('v22QrScanInput').focus()"));
console.log('THORIN HID scan regression tests passed (FA layout, receive, handover, release, name entry, paste).');
